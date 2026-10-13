# Evaluating the news agent

"Does it work?" is too vague to answer. These scripts split it into questions
that can each be measured, from cheapest to most expensive.

| Level | Question | How | Script |
|---|---|---|---|
| 1 | Is the output well-formed? | Plain code rules | `check_items.py` |
| 2 | Are the category and status right? Would I publish it? | My own labels (the "golden set") | `make_labels.py` → `score.py` |
| 3 | Is every fact in the summary really in the article? | A bigger model as judge, checked against my labels | `judge.py` → `score.py` |

## How to run

```bash
python evals/check_items.py   # 1. rules, no API, 1 second
python evals/make_labels.py   # 2. creates evals/labels.csv
#    open labels.csv, read each original article, fill in the empty columns
python evals/judge.py         # 3. AI judge (uses GROQ_API_KEY), writes judge_report.json
python evals/score.py         # scores everything against my labels
```

`judge.py --limit 3` judges only 3 stories, for a cheap test. `judge.py --dry-run`
prints the judge prompt without calling the API.

## Why each piece is built this way

- **Blind labeling.** `labels.csv` doesn't show the agent's answers, so they can't
  nudge mine. `score.py` joins them afterwards by link.
- **The judge must be checked too.** An AI judge is only useful if it agrees with
  a human. `score.py` reports how often the judge's verdict matches mine, and
  whether it catches the stories I marked unfaithful. If it does, I can let the judge
  check new stories automatically and only spot-check by hand.
- **The judge is a bigger model** (`openai/gpt-oss-120b` by default, change it with
  `JUDGE_MODEL`) than the agent (`gpt-oss-20b`). A model grading its own work tends
  to miss its own mistakes.
- **Articles are cached** in `evals/cache/`, so comparing two prompt versions
  uses exactly the same source text.
- **Numbers are checked by code**, not AI: every number in a summary must appear in
  the article. Numbers are where invented facts are easiest to spot.

## The loop

1. Run all levels and write down the scores (baseline).
2. Read the disagreements `score.py` prints. Group them: what kind of mistake is it?
3. Change one thing (the prompt, the model, a rule).
4. Rerun on the same labeled stories. Compare to the baseline.

## What this can't measure yet

The site only shows what the agent published. The headlines it **skipped**, and the
reasons, are only printed in the GitHub Actions log and then lost. So I can measure
precision (of what it published, how much was good) but not recall (good stories it
missed). Next step: save a log per run (headlines, chosen, skipped with reasons,
the article text the writer saw) so the choosing step can be evaluated too.