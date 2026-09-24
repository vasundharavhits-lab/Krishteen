"""
finetune_qwen.py — LoRA fine-tune Qwen2.5-1.5B-Instruct on krishteen_finetune_dataset_v2.jsonl

Designed to run on a free Google Colab T4 GPU (or any machine with ~6GB+ VRAM).
Uses Unsloth, which is by far the least painful way to fine-tune a small
Qwen model and get a clean merged model back out.

v2 dataset = original 29 seed examples + 22 cleaned/deduped examples pulled from
conversation_logs.jsonl (51 total). Still a SMALL dataset by ML standards, not
"large" — no streaming or chunked loading needed, it's tiny enough to load in
one shot. What changed vs. v1 is mainly: more topic diversity, so epochs are
trimmed slightly (below) to avoid memorizing 51 examples too hard, and
checkpointing now saves to Drive so a Colab disconnect doesn't lose the run.

Before adding more logs later, re-run the same cleaning pass this dataset went
through: drop near-duplicate questions, drop any turn logged without its
preceding context (these show up as a short/garbled user message paired with
an answer that doesn't match it), and sanity-check factual answers (one dropped
example had 4 + 50 + 90 answered as 54).

Install (Colab / fresh venv):
    pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
    pip install --no-deps trl peft accelerate bitsandbytes

Run:
    python finetune_qwen.py
"""

from unsloth import FastLanguageModel
from trl import SFTTrainer, SFTConfig
from datasets import load_dataset
import torch

MAX_SEQ_LEN = 2048
BASE_MODEL = "unsloth/Qwen2.5-1.5B-Instruct"  # matches qwen2.5:1.5b in Ollama
OUTPUT_DIR = "krishteen-qwen2.5-1.5b-lora-v2"
DATASET_FILE = "krishteen_finetune_dataset_v2.jsonl"

# Colab session can drop mid-run; checkpoints go to Drive so training can
# resume instead of starting over. Mount Drive before running this script:
#   from google.colab import drive
#   drive.mount('/content/drive')
CHECKPOINT_DIR = "/content/drive/MyDrive/krishteen-checkpoints"

# 1. Load base model in 4-bit (fits comfortably even on a free-tier GPU)
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE_MODEL,
    max_seq_length=MAX_SEQ_LEN,
    load_in_4bit=True,
)

# 2. Attach LoRA adapters — small model, so keep rank modest to avoid
# overfitting on a dataset this size (51 examples — bigger than v1's 29, but
# still small; keep expanding via cleaned conversation logs over time).
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
    lora_alpha=16,
    lora_dropout=0.05,
    bias="none",
    use_gradient_checkpointing="unsloth",
)

# 3. Load the dataset and format each example with Qwen's chat template
dataset = load_dataset("json", data_files=DATASET_FILE, split="train")


def format_example(example):
    text = tokenizer.apply_chat_template(
        example["messages"], tokenize=False, add_generation_prompt=False
    )
    return {"text": text}


dataset = dataset.map(format_example)

# 4. Train
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LEN,
    args=SFTConfig(
        output_dir=CHECKPOINT_DIR,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        num_train_epochs=2,          # dropped from 3 -> 2: more diverse data now,
                                      # so fewer passes are needed before it starts
                                      # memorizing instead of generalizing
        learning_rate=2e-4,
        warmup_steps=5,
        logging_steps=1,
        save_strategy="steps",
        save_steps=20,
        save_total_limit=3,
        optim="adamw_8bit",
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
    ),
)

trainer.train(resume_from_checkpoint=True if __import__("os").path.isdir(CHECKPOINT_DIR) and
              __import__("os").listdir(CHECKPOINT_DIR) else None)

# 5. Save merged (base + LoRA) model in 16-bit — this is what you convert to GGUF next
model.save_pretrained_merged(
    f"{OUTPUT_DIR}-merged", tokenizer, save_method="merged_16bit"
)

print(f"\nDone. Merged model saved to ./{OUTPUT_DIR}-merged")
print(f"Checkpoints are also in {CHECKPOINT_DIR} on Drive if you need to resume or roll back.")
print("Next: convert to GGUF and import into Ollama — see README.md")