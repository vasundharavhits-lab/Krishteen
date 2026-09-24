"""
Run this in Colab. Blends 300 sampled examples from a public Hinglish
conversational dataset with your existing 41 Krishteen-specific examples,
to add general casual-tone fluency without losing persona/identity data.
"""
from datasets import load_dataset
import json, random

random.seed(42)

# 1. Load your existing curated dataset (upload krishteen_finetune_dataset_v2.jsonl first)
existing = []
with open("krishteen_finetune_dataset_v2.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            existing.append(json.loads(line))
print("Existing Krishteen examples:", len(existing))

# 2. Load and sample from the public Hinglish dataset
public_ds = load_dataset("Abhishekcr448/Hinglish-Everyday-Conversations-1M", split="train")
print("Public dataset total rows:", len(public_ds))

SAMPLE_SIZE = 300
indices = random.sample(range(len(public_ds)), SAMPLE_SIZE)
sampled = public_ds.select(indices)

converted = []
for row in sampled:
    user_text = (row.get("input") or "").strip()
    asst_text = (row.get("output") or "").strip()
    if not user_text or not asst_text:
        continue
    # basic length sanity filter -- skip anything absurdly short/long
    if len(user_text) < 3 or len(asst_text) < 3:
        continue
    if len(asst_text) > 600:
        continue
    converted.append({
        "messages": [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": asst_text},
        ]
    })

print("Converted public examples (after filtering):", len(converted))

# 3. Combine and dedupe
combined = existing + converted
seen = set()
deduped = []
for e in combined:
    key = json.dumps(e["messages"], sort_keys=True)
    if key in seen:
        continue
    seen.add(key)
    deduped.append(e)

print("Final combined dataset:", len(deduped))

with open("krishteen_finetune_dataset_v3.jsonl", "w", encoding="utf-8") as f:
    for e in deduped:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")

print("Wrote krishteen_finetune_dataset_v3.jsonl")