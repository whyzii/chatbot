"""Level 2 eval, step 1: create the labeling sheet for your golden set.

Writes evals/labels.csv with one row per published story. YOU fill in the
empty columns by reading each original article. Your answers are the "ground
truth" that the agent is measured against.

The sheet deliberately does NOT show the agent's answers, so they can't
influence yours ("blind labeling"). score.py compares them afterwards.

Running it again only adds new stories; rows you already labeled are kept.

Run:  python evals/make_labels.py
Then open evals/labels.csv in Numbers / Excel / Google Sheets and fill in:
  my_category      New models | Research | Tools and products | Industry and funding | Policy and safety
  my_status        official | reported | rumor
  should_publish   yes | no      (is this real news worth a spot on the site?)
  faithful         yes | minor | no   (compare the agent's summary with the article:
                                       any invented or wrong name, number, date, actor = no)
  notes            anything you noticed
Fill faithful last: it's the one column where you do need to read the agent's summary.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED_PATH = ROOT / "published.json"
LABELS_PATH = ROOT / "evals" / "labels.csv"

COLUMNS = ["source_url", "headline", "my_category", "my_status",
           "should_publish", "faithful", "notes"]


def main():
    items = [item for item in json.loads(PUBLISHED_PATH.read_text())
             if item.get("decision") == "publish"]

    rows = []
    if LABELS_PATH.exists():
        with LABELS_PATH.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    known = {row["source_url"] for row in rows}

    added = 0
    for item in items:
        url = item.get("source_url", "")
        if url in known:
            continue
        # Show the URL slug as the headline, not the agent's rewritten title
        headline = url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
        rows.append({"source_url": url, "headline": headline})
        known.add(url)
        added += 1

    LABELS_PATH.parent.mkdir(exist_ok=True)
    with LABELS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in COLUMNS})

    print(f"{LABELS_PATH.relative_to(ROOT)}: {len(rows)} rows ({added} new). Fill in the empty columns.")


if __name__ == "__main__":
    main()