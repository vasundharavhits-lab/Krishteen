"""
Computes accuracy using sklearn on top of test_results_scored.csv
(the file produced by score_accuracy.py, which already has a
'verdict' column: CORRECT / INCORRECT / MANUAL_REVIEW).

Usage:
    python sklearn_accuracy.py test_results_scored.csv
"""

import sys
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix

INPUT_CSV = sys.argv[1] if len(sys.argv) > 1 else "test_results_scored.csv"

df = pd.read_csv(INPUT_CSV)

# Only objectively-graded rows count toward accuracy (MANUAL_REVIEW excluded,
# same rule as before — there's no single right answer for those).
graded = df[df["verdict"].isin(["CORRECT", "INCORRECT"])].copy()

# sklearn's accuracy_score needs a "true" label array and a "predicted" array.
# Here, y_true is "what it should have been" (always CORRECT, since that's
# the target outcome) and y_pred is the verdict we actually got.
y_true = ["CORRECT"] * len(graded)
y_pred = graded["verdict"].tolist()

overall_acc = accuracy_score(y_true, y_pred)
print(f"Overall accuracy (sklearn): {overall_acc:.1%}  "
      f"({(graded['verdict'] == 'CORRECT').sum()}/{len(graded)} graded questions)\n")

# Per-category accuracy, same idea, grouped.
print(f"{'Category':40s} {'Accuracy':>10s} {'N graded':>10s}")
for category, group in graded.groupby("category"):
    y_true_cat = ["CORRECT"] * len(group)
    y_pred_cat = group["verdict"].tolist()
    acc = accuracy_score(y_true_cat, y_pred_cat)
    print(f"{category:40s} {acc:10.1%} {len(group):10d}")

# Confusion-style matrix: category (rows) x verdict (columns).
# Not a classic confusion matrix (different label spaces), but sklearn's
# confusion_matrix works fine as a general cross-tabulation tool here.
print("\nCategory x Verdict breakdown:")
labels = sorted(df["verdict"].unique())
cm = confusion_matrix(df["category"], df["verdict"], labels=None)
# Easier to read via pandas crosstab than raw sklearn output:
print(pd.crosstab(df["category"], df["verdict"]))
