import json

with open("krishteen_finetune_dataset_v12.jsonl", encoding="utf-8") as f:
    for i, line in enumerate(f):
        entry = json.loads(line)
        msgs = entry["messages"]
        user_msg = ""
        for msg in msgs:
            if msg["role"] == "user":
                user_msg = msg["content"].lower()
        if "who made you" in user_msg or "your name" in user_msg or "kisne banaya" in user_msg:
            for msg in msgs:
                if msg["role"] == "assistant":
                    print("Line", i)
                    print("USER:", user_msg)
                    print("ASSISTANT:", msg["content"])
                    print("---")
