"""Level 3 eval: LLM-as-judge for faithfulness.

For each published item, a bigger "judge" model reads the source article and the
item your agent wrote, and checks every factual claim against the article.

Two checks run on each item:
  1. Number check (plain code): every number in the item must appear in the article.
  2. Judge (AI): is each claim supported? Is the right organization credited?
     Is the status label (official / reported / rumor) right?

Run:
  python evals/judge.py              # all published items
  python evals/judge.py --limit 3    # first 3 only (cheap test)
  python evals/judge.py --dry-run    # print the judge prompt for item 0, no API call

Needs GROQ_API_KEY in .env. Optional JUDGE_MODEL (default below).
Articles are cached in evals/cache/, so rerunning compares against the same text.
Output: evals/judge_report.json
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import fetch_article  # noqa: E402

PUBLISHED_PATH = ROOT / "published.json"
CACHE_DIR = ROOT / "evals" / "cache"
REPORT_PATH = ROOT / "evals" / "judge_report.json"

# The judge should be stronger than the model it grades (your agent uses gpt-oss-20b).
DEFAULT_JUDGE_MODEL = "openai/gpt-oss-120b"

JUDGE_PROMPT = """You are a strict fact-checker for a news website. You receive a SOURCE ARTICLE and a NEWS ITEM that a writer produced from it. The writer was told to use ONLY facts from the article.

Check the NEWS ITEM:

1. CLAIMS. Split the title, summary and why_it_matters into individual factual claims (who did what, names, numbers, dates, what a product does, what a study found). For each claim decide:
   - "supported": the article says this, possibly in other words
   - "unsupported": the article does not say this (even if it might be true)
   - "contradicted": the article says something different
   An opinion about why the news matters is fine and is not a factual claim, unless it states a new fact.
   A claim that the article attributes to someone ("Mistral says X") but the item states as plain fact ("X") is "unsupported".

2. ATTRIBUTION. Is the organization credited in the item the one that actually made the news, according to the article? (A news site or blog platform that only hosts the story should not be credited as the maker.)

3. STATUS. The item has a status label. Is it right?
   - "official": the company or organization announced or published it (even if reported by a news site)
   - "reported": a news outlet reports it, with no official announcement in the article
   - "rumor": leaks, unconfirmed claims, or "sources say"

4. VERDICT for the whole item:
   - "faithful": every factual claim is supported
   - "minor_issues": only small problems (slight overstatement, vague wording) with no wrong names, numbers, dates or actors
   - "unfaithful": at least one wrong or invented name, number, date, actor, or claim

Reply ONLY with JSON:
{"claims": [{"text": "...", "verdict": "supported|unsupported|contradicted", "note": "short reason"}],
 "attribution_ok": true, "attribution_note": "...",
 "status_ok": true, "correct_status": "official|reported|rumor", "status_note": "...",
 "verdict": "faithful|minor_issues|unfaithful"}"""


def get_source_text(url: str) -> str:
    """Fetch the article once and keep a copy, so every rerun judges against the same text."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt")
    if path.exists():
        return path.read_text(encoding="utf-8")
    text = fetch_article(url, max_chars=12000)
    path.write_text(text, encoding="utf-8")
    return text


def numbers_missing_from_source(item: dict, source: str) -> list[str]:
    """Numbers in the item (like 507, 2030, $1B, 10,000) that never appear in the article."""
    text = " ".join(str(item.get(f, "")) for f in ("title", "summary", "why_it_matters"))
    source_digits = source.replace(",", "")
    missing = []
    for number in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text):
        plain = number.replace(",", "")
        if plain not in source_digits:
            missing.append(number)
    return sorted(set(missing))


def item_for_judge(item: dict) -> str:
    keep = ("title", "summary", "why_it_matters", "category", "status", "source")
    return json.dumps({k: item.get(k, "") for k in keep}, indent=2, ensure_ascii=False)


def parse_json(text: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", text or "").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    try:
        return json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return {}


def judge_item(client, model: str, item: dict, source: str) -> dict:
    messages = [
        {"role": "system", "content": JUDGE_PROMPT},
        {"role": "user", "content": f"SOURCE ARTICLE:\n{source}\n\nNEWS ITEM:\n{item_for_judge(item)}"},
    ]
    response = client.chat.completions.create(
        model=model, messages=messages, temperature=0,
        response_format={"type": "json_object"},
    )
    return parse_json(response.choices[0].message.content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only judge the first N items")
    parser.add_argument("--dry-run", action="store_true", help="print the prompt for item 0 and stop")
    args = parser.parse_args()

    items = [(i, item) for i, item in enumerate(json.loads(PUBLISHED_PATH.read_text()))
             if item.get("decision") == "publish"]
    if args.limit:
        items = items[:args.limit]

    if args.dry_run:
        i, item = items[0]
        print(JUDGE_PROMPT, "\n\n---\nNEWS ITEM:\n", item_for_judge(item))
        return

    # pyrefly: ignore [missing-import]
    from dotenv import load_dotenv
    # pyrefly: ignore [missing-import]
    from groq import Groq
    load_dotenv(ROOT / ".env", override=True)
    client = Groq(api_key=os.environ["GROQ_API_KEY"].strip(), max_retries=5)
    model = os.environ.get("JUDGE_MODEL", DEFAULT_JUDGE_MODEL).strip()
    print(f"Judge model: {model}\n")

    report = []
    for i, item in items:
        source = get_source_text(item["source_url"])
        row = {"id": i, "title": item.get("title"), "source_url": item["source_url"]}

        if source.startswith("[The article could not be downloaded"):
            row["verdict"] = "no_source"
        else:
            row["only_feed_summary"] = source.startswith("[The full article could not")
            row["numbers_not_in_source"] = numbers_missing_from_source(item, source)
            try:
                row.update(judge_item(client, model, item, source))
            except Exception as e:
                row["verdict"] = "judge_error"
                row["error"] = str(e)

        report.append(row)
        bad = [c for c in row.get("claims", []) if c.get("verdict") != "supported"]
        print(f"#{i:<3} {row.get('verdict', '?'):13} {item.get('title', '')[:70]}")
        for claim in bad:
            print(f"       {claim.get('verdict')}: {claim.get('text')}  ({claim.get('note')})")
        if row.get("attribution_ok") is False:
            print(f"       attribution: {row.get('attribution_note')}")
        if row.get("status_ok") is False:
            print(f"       status should be '{row.get('correct_status')}': {row.get('status_note')}")
        if row.get("only_feed_summary"):
            print("       (only the short feed summary was available to check against)")
        if row.get("numbers_not_in_source"):
            print(f"       numbers not found in article: {row['numbers_not_in_source']}")

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # Totals
    judged = [r for r in report if r.get("verdict") in ("faithful", "minor_issues", "unfaithful")]
    claims = [c for r in judged for c in r.get("claims", [])]
    supported = sum(c.get("verdict") == "supported" for c in claims)
    print("\n" + "-" * 60)
    for verdict in ("faithful", "minor_issues", "unfaithful"):
        print(f"{verdict:13} {sum(r['verdict'] == verdict for r in judged)} / {len(judged)}")
    if claims:
        print(f"claims supported: {supported}/{len(claims)} ({supported / len(claims):.0%})")
    print(f"attribution wrong: {sum(r.get('attribution_ok') is False for r in judged)}")
    print(f"status wrong:      {sum(r.get('status_ok') is False for r in judged)}")
    print(f"\nFull report: {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
    