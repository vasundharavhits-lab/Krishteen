"""
Scores test_results.csv for accuracy using an answer key.

- Objective questions (facts, math, logic, code, programming) are auto-graded
  by checking whether the response contains the expected answer (case-insensitive
  substring match, or a custom check function for special cases).
- Subjective / open-ended questions (ambiguous, contradiction-handling,
  real-world reasoning) have no single right answer, so they're marked
  MANUAL_REVIEW instead of guessed at.

Usage:
    python score_accuracy.py test_results.csv
"""

import csv
import re
import sys

INPUT_CSV = sys.argv[1] if len(sys.argv) > 1 else "test_results.csv"
OUTPUT_CSV = "test_results_scored.csv"


# ---------------- Answer key ----------------
# Maps a question (exact text as it appears in the CSV) to either:
#   - a list of acceptable substrings (any one match => correct), or
#   - a callable(response_text) -> bool for custom logic

def word_count_is(n):
    def check(text):
        # crude but workable: count words in the first line/sentence only,
        # ignoring markdown/punctuation-only tokens
        words = [w for w in re.findall(r"[A-Za-z0-9']+", text)]
        return len(words) == n
    return check


def sentence_count_is(n):
    def check(text):
        sentences = [s for s in re.split(r"[.!?]+", text.strip()) if s.strip()]
        return len(sentences) == n
    return check


def row_count_is(n):
    def check(text):
        rows = [l for l in text.splitlines() if l.strip().startswith("|")]
        # subtract header + separator row if present
        data_rows = max(0, len(rows) - 2) if len(rows) >= 2 else len(rows)
        return data_rows == n
    return check


def is_valid_json_only(text):
    stripped = text.strip().strip("`").strip()
    if stripped.startswith("json"):
        stripped = stripped[4:].strip()
    import json
    try:
        json.loads(stripped)
        return True
    except Exception:
        return False


ANSWER_KEY = {
    # 1. Basic factual accuracy
    "What is the capital of France?": ["paris"],
    "What is the largest planet in our solar system?": ["jupiter"],
    "Who wrote Pride and Prejudice?": ["jane austen"],
    "What is the chemical symbol for gold?": ["au"],
    "How many continents are there?": ["seven", "7"],
    "What is the boiling point of water at sea level?": ["100°c", "100 °c", "100c", "212°f", "212 °f", "212f"],
    "Who painted the Mona Lisa?": ["leonardo da vinci", "da vinci"],
    "What is the smallest prime number?": ["2"],
    "Which planet is known as the Red Planet?": ["mars"],
    "What is the currency of Japan?": ["yen"],

    # 2. Science
    "Why does ice float on water?": ["less dense", "density"],
    "What is photosynthesis?": ["light", "energy", "glucose", "sugar"],
    "What is the difference between DNA and RNA?": ["deoxyribonucleic", "ribonucleic"],
    "Why is the sky blue?": ["rayleigh", "scatter"],
    "What causes gravity?": ["mass"],
    "What is the function of mitochondria?": ["atp", "energy"],
    "What is an electron?": ["negative", "charge", "subatomic"],
    "What is the difference between a virus and a bacterium?": ["cell", "replicat"],
    "What happens to water molecules when water freezes?": ["crystal", "lattice", "structure", "slow"],
    "Can humans breathe pure oxygen safely for extended periods?": ["no", "toxic", "danger"],

    # 3. Mathematics and reasoning
    "What is 17 x 24?": ["408"],
    "What is 15% of 860?": ["129"],
    "If a train travels 120 km in 2 hours, what is its average speed?": ["60"],
    "A product costs Rs 1200 and has a 20% discount. What is the final price?": ["960"],
    "If x + 7 = 19, what is x?": word_count_is,  # placeholder, replaced below
    "What is the next number: 2, 6, 12, 20, 30, ?": ["42"],
    "If 5 workers complete a task in 12 days, assuming equal productivity, how long would 10 workers take?": ["6"],
    "A clock shows 3:15. What is the approximate angle between the hour and minute hands?": ["7.5", "7 .5"],
    "If today is Wednesday, what day will it be 100 days from now?": ["friday"],
    "A box contains 3 red, 5 blue, and 2 green balls. What is the probability of randomly selecting a blue ball?": ["1/2", "0.5", "50%"],

    # 4. Logic
    "All cats are animals. Some animals are black. Can we conclude that some cats are black?": ["no", "cannot", "can't"],
    "If A is taller than B and B is taller than C, who is shortest?": ["c"],
    "A farmer has 10 sheep. All but 3 die. How many remain?": ["3", "three"],
    "If five machines make five products in five minutes, how long would 100 machines take to make 100 products?": ["5 minutes", "five minutes"],
    "What comes next: A, C, F, J, O, ?": ["u"],
    "If yesterday was Monday, what day is tomorrow?": ["wednesday"],
    "A doctor gives you three pills and tells you to take one every 30 minutes. How long will the pills last?": ["60 minutes", "1 hour", "one hour"],
    "Which is heavier: 1 kg of iron or 1 kg of feathers?": ["same", "equal"],
    "If you overtake the person in second place in a race, what position are you in?": ["second"],

    # 9. Instruction-following (custom checks)
    "Answer the following question using exactly five words: What is artificial intelligence?": word_count_is(5),
    "Explain gravity in exactly two sentences.": sentence_count_is(2),
    "Give me a table with exactly three rows.": row_count_is(3),
    "Return the answer as JSON.": is_valid_json_only,
    "Answer only with \"YES\" or \"NO\": Is water wet?": lambda t: t.strip().upper() in ("YES", "NO"),

    # 11. Code reasoning
    "What does this output?\nx = [1, 2, 3]\ny = x\ny.append(4)\nprint(x)": ["[1, 2, 3, 4]"],
    "What does this output?\nprint(0.1 + 0.2 == 0.3)": ["false"],
    "What will happen?\nx = None\nif x:\n    print(\"A\")\nelse:\n    print(\"B\")": ["b"],
}

# fix the x+7=19 entry (accidentally left as placeholder above)
ANSWER_KEY["If x + 7 = 19, what is x?"] = ["x = 12", "x=12", "12"]


def grade(question, response):
    key = ANSWER_KEY.get(question.strip())
    if key is None:
        return "MANUAL_REVIEW"
    text = response.lower() if isinstance(key, list) else response
    if callable(key):
        try:
            return "CORRECT" if key(response) else "INCORRECT"
        except Exception:
            return "INCORRECT"
    for expected in key:
        pattern = r"\b" + re.escape(expected.lower()) + r"\b"
        if re.search(pattern, text):
            return "CORRECT"
    return "INCORRECT"


def main():
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    scored = []
    for r in rows:
        verdict = grade(r["question"], r["model_response"])
        r["verdict"] = verdict
        scored.append(r)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "category", "question", "model_response", "verdict"])
        writer.writeheader()
        writer.writerows(scored)

    # ---- summary ----
    from collections import defaultdict
    by_cat = defaultdict(lambda: {"CORRECT": 0, "INCORRECT": 0, "MANUAL_REVIEW": 0})
    for r in scored:
        by_cat[r["category"]][r["verdict"]] += 1

    print(f"{'Category':40s} {'Correct':>8s} {'Wrong':>8s} {'Review':>8s} {'Auto-Acc':>10s}")
    total_correct = total_graded = 0
    for cat, counts in by_cat.items():
        graded = counts["CORRECT"] + counts["INCORRECT"]
        acc = f"{100*counts['CORRECT']/graded:.0f}%" if graded else "n/a"
        print(f"{cat:40s} {counts['CORRECT']:8d} {counts['INCORRECT']:8d} {counts['MANUAL_REVIEW']:8d} {acc:>10s}")
        total_correct += counts["CORRECT"]
        total_graded += graded

    overall = 100 * total_correct / total_graded if total_graded else 0
    print(f"\nAuto-graded accuracy: {total_correct}/{total_graded} = {overall:.1f}%")
    print(f"(Questions marked MANUAL_REVIEW have no single right answer and are excluded from this %.)")
    print(f"\nFull results with verdicts saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
