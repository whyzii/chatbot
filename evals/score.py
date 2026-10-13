"""Level 2 eval, step 2: score the agent against your labels.

Reads evals/labels.csv (your answers) and published.json (the agent's answers),
and, if it exists, evals/judge_report.json (the AI judge's verdicts).

Prints:
  - category and status accuracy, with a confusion matrix
  - how many published stories you would have published (choosing precision)
  - how faithful the summaries are, by your own reading
  - how often the AI judge agrees with you (can you trust the judge?)
  - every disagreement, so you can look at the actual mistakes

Run:  python evals/score.py
"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED_PATH = ROOT / "published.json"
LABELS_PATH = ROOT / "evals" / "labels.csv"
REPORT_PATH = ROOT / "evals" / "judge_report.json"

CATEGORIES = ["New models", "Research", "Tools and products", "Industry and funding", "Policy and safety"]
SHORT = {"New models": "Models", "Research": "Research", "Tools and products": "Tools",
         "Industry and funding": "Industry", "Policy and safety": "Policy"}
STATUSES = ["official", "reported", "rumor"]
JUDGE_TO_HUMAN = {"faithful": "yes", "minor_issues": "minor", "unfaithful": "no"}


def norm(value: str) -> str:
    return (value or "").strip().lower()


def accuracy(pairs: list[tuple[str, str]]) -> str:
    if not pairs:
        return "no labels yet"
    right = sum(norm(mine) == norm(agent) for mine, agent in pairs)
    return f"{right}/{len(pairs)} = {right / len(pairs):.0%}"


def confusion(pairs: list[tuple[str, str]], labels: list[str], short=None):
    """Rows: your label. Columns: the agent's label. The diagonal is where you agree."""
    short = short or {label: label for label in labels}
    counts = Counter((norm(m), norm(a)) for m, a in pairs)
    width = max(len(s) for s in short.values()) + 2
    print(" " * width + "agent →")
    print("you ↓".ljust(width) + "".join(short[l].rjust(width) for l in labels))
    for mine in labels:
        row = "".join(str(counts[(norm(mine), norm(a))] or ".").rjust(width) for a in labels)
        print(short[mine].ljust(width) + row)


def main():
    if not LABELS_PATH.exists():
        print("No labels yet. Run: python evals/make_labels.py, then fill in evals/labels.csv")
        return

    agent = {item.get("source_url"): item for item in json.loads(PUBLISHED_PATH.read_text())}
    judge = {}
    if REPORT_PATH.exists():
        judge = {row["source_url"]: row for row in json.loads(REPORT_PATH.read_text())}

    with LABELS_PATH.open(newline="", encoding="utf-8") as f:
        labels = [row for row in csv.DictReader(f) if row["source_url"] in agent]

    category = [(r["my_category"], agent[r["source_url"]].get("category", ""), r)
                for r in labels if r["my_category"].strip()]
    status = [(r["my_status"], agent[r["source_url"]].get("status", ""), r)
              for r in labels if r["my_status"].strip()]
    publish = [norm(r["should_publish"]) for r in labels if r["should_publish"].strip()]
    faithful = [norm(r["faithful"]) for r in labels if r["faithful"].strip()]

    print(f"Labeled stories: {len(labels)}")
    if labels:
        print(f"(small sample: one mistake moves a score by {1 / len(labels):.0%})\n")

    print("== Category ==")
    print("accuracy:", accuracy([(m, a) for m, a, _ in category]))
    if category:
        confusion([(m, a) for m, a, _ in category], CATEGORIES, SHORT)

    print("\n== Status (official / reported / rumor) ==")
    print("accuracy:", accuracy([(m, a) for m, a, _ in status]))
    if status:
        confusion([(m, a) for m, a, _ in status], STATUSES)

    print("\n== Choosing ==")
    if publish:
        yes = publish.count("yes")
        print(f"stories you'd also publish: {yes}/{len(publish)} = {yes / len(publish):.0%}  (precision)")
        print("(recall, the good stories it missed, needs the skipped headlines: see README)")

    print("\n== Faithfulness (your reading) ==")
    if faithful:
        counts = Counter(faithful)
        for key in ("yes", "minor", "no"):
            print(f"{key:6} {counts[key]}/{len(faithful)}")

    # Can the AI judge replace you? Only if it agrees with you on the stories you both checked.
    both = [(norm(r["faithful"]), JUDGE_TO_HUMAN.get(judge[r["source_url"]].get("verdict")), r)
            for r in labels
            if r["faithful"].strip() and r["source_url"] in judge
            and judge[r["source_url"]].get("verdict") in JUDGE_TO_HUMAN]
    if both:
        exact = sum(mine == j for mine, j, _ in both)
        # The question that matters most: does the judge catch the bad ones?
        bad_mine = [(mine, j) for mine, j, _ in both if mine == "no"]
        caught = sum(j == "no" for _, j in bad_mine)
        print("\n== AI judge vs you ==")
        print(f"same verdict: {exact}/{len(both)} = {exact / len(both):.0%}")
        if bad_mine:
            print(f"unfaithful stories the judge also caught: {caught}/{len(bad_mine)}")

    # The most useful part: the actual mistakes
    print("\n== Disagreements to look at ==")
    shown = False
    for mine, got, r in category:
        if norm(mine) != norm(got):
            print(f"category  you: {mine:20} agent: {got:20} {r['headline'][:50]}")
            shown = True
    for mine, got, r in status:
        if norm(mine) != norm(got):
            print(f"status    you: {mine:20} agent: {got:20} {r['headline'][:50]}")
            shown = True
    for mine, j, r in both:
        if mine != j:
            print(f"judge     you: {mine:20} judge: {j:20} {r['headline'][:50]}")
            shown = True
    if not shown:
        print("(none)")


if __name__ == "__main__":
    main()