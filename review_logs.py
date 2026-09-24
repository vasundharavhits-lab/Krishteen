"""
review_logs.py — walks through conversation_logs.jsonl (written by ai.py's
_log_exchange) one entry at a time, lets you skip, accept as-is, or edit
the assistant reply, then appends anything you keep to
krishteen_finetune_dataset.jsonl in the same format dataset_builder.py uses.

This is the "curate real transcripts" step from the README — run it
periodically as conversation_logs.jsonl fills up.

Run:
    python review_logs.py
"""

import json
import os

LOG_PATH = "conversation_logs.jsonl"
DATASET_PATH = "krishteen_finetune_dataset.jsonl"


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    entries = load_jsonl(LOG_PATH)
    if not entries:
        print(f"No entries found in {LOG_PATH} yet — run Krishteen a bit first.")
        return

    print(f"{len(entries)} logged exchanges found.\n")
    kept = 0

    for i, entry in enumerate(entries, 1):
        messages = entry.get("messages", [])
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
        assistant_msg = next((m["content"] for m in messages if m["role"] == "assistant"), "")

        print(f"--- [{i}/{len(entries)}] {entry.get('timestamp', '')} "
              f"(handled_by={entry.get('handled_by')}, style={entry.get('style')}, role={entry.get('role')}) ---")
        print(f"User:      {user_msg}")
        print(f"Assistant: {assistant_msg}")
        choice = input("Keep as-is [y] / Edit reply [e] / Skip [n/enter]: ").strip().lower()

        if choice == "y":
            append_jsonl(DATASET_PATH, {"messages": messages})
            kept += 1
        elif choice == "e":
            corrected = input("New assistant reply: ").strip()
            if corrected:
                fixed_messages = [m for m in messages if m["role"] != "assistant"]
                fixed_messages.append({"role": "assistant", "content": corrected})
                append_jsonl(DATASET_PATH, {"messages": fixed_messages})
                kept += 1
        print()

    print(f"Done. Added {kept} example(s) to {DATASET_PATH}.")
    print(f"Tip: once you're happy with these, clear or archive {LOG_PATH} so the "
          f"next review pass doesn't re-show the same entries.")


if __name__ == "__main__":
    main()