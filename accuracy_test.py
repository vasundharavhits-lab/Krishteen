import requests
from sklearn.metrics import accuracy_score

# ---- Test cases: (prompt, keywords that MUST appear in a correct answer) ----
test_cases = [
    {
        "prompt": "who made you?",
        "expected_keywords": ["virtual height"],
    },
    {
        "prompt": "what is your name?",
        "expected_keywords": ["krishteen"],
    },
    {
        "prompt": "Give me three Python frameworks and nothing else.",
        "expected_keywords": ["flask", "django", "fastapi"],
    },
    {
        "prompt": "Answer only with 'YES' or 'NO': Is water wet?",
        "expected_keywords": ["yes"],
    },
    {
        "prompt": "Explain gravity in exactly two sentences.",
        "expected_keywords": ["gravity"],
    },
]

MODEL_NAME = "krishteen"
OLLAMA_URL = "http://localhost:11434/api/generate"


def get_model_response(prompt: str) -> str:
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
        },
    )
    response.raise_for_status()
    return response.json()["response"]


def evaluate(test_cases):
    y_true = []   # ground truth: hamesha 1 (correct answer possible)
    y_pred = []   # model actually sahi bola ya nahi (1 = sahi, 0 = galat)

    for case in test_cases:
        prompt = case["prompt"]
        keywords = case["expected_keywords"]

        model_output = get_model_response(prompt)
        output_lower = model_output.lower()

        # Check: kya expected keywords me se koi bhi output me mila?
        is_correct = any(keyword.lower() in output_lower for keyword in keywords)

        y_true.append(1)
        y_pred.append(1 if is_correct else 0)

        print(f"Prompt: {prompt}")
        print(f"Model response: {model_output.strip()}")
        print(f"Correct: {is_correct}")
        print("-" * 50)

    return y_true, y_pred


if __name__ == "__main__":
    y_true, y_pred = evaluate(test_cases)

    acc = accuracy_score(y_true, y_pred)
    print(f"\nTotal test cases: {len(test_cases)}")
    print(f"Accuracy: {acc * 100:.2f}%")
