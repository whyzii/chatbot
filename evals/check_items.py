"""Level 1 eval: rule checks on published.json. No AI, no internet, runs in a second.

These catch mistakes that plain code can detect for sure: missing fields,
invented category names, a link that doesn't match its source, duplicates,
hype words, summaries that are too long.

Run:  python evals/check_items.py
Exit code is 1 if any ERROR is found, so it can block a bad publish in GitHub Actions.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import FEEDS  # noqa: E402  (the news sources the agent reads)

PUBLISHED_PATH = ROOT / "published.json"

CATEGORIES = {"New models", "Research", "Tools and products",
              "Industry and funding", "Policy and safety"}
STATUSES = {"official", "reported", "rumor"}
REQUIRED = ["decision", "reason", "category", "status", "title", "summary",
            "why_it_matters", "source", "source_url", "published"]
HYPE_WORDS = ["revolutionary", "game-changer", "game changer", "insane", "groundbreaking",
              "unprecedented", "mind-blowing", "breakthrough", "stunning", "massive"]

# News outlets report news; companies announce it. An outlet story marked
# "official" is not always wrong, but it is worth a human look.
NEWS_OUTLETS = {"Ars Technica"}

# Each source's website, taken from its feed URL (for example "arstechnica.com")
SOURCE_DOMAINS = {name: urlparse(url).netloc.removeprefix("www.") for name, url in FEEDS.items()}


def count_sentences(text: str) -> int:
    """Rough sentence count: split after . ! ? when followed by a space and a capital letter."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text.strip())
    return len([p for p in parts if p])


def check_item(item: dict, seen_urls: set) -> list[tuple[str, str]]:
    """Return a list of (level, message) problems for one item."""
    problems = []
    error = lambda msg: problems.append(("ERROR", msg))
    warn = lambda msg: problems.append(("WARN", msg))

    if item.get("decision") != "publish":
        return problems   # needs_review items have a smaller format; skip them here

    # 1. Format: every field present and filled
    for field in REQUIRED:
        if not str(item.get(field, "")).strip():
            error(f"missing field '{field}'")

    # 2. Allowed values only
    if item.get("category") not in CATEGORIES:
        error(f"unknown category '{item.get('category')}'")
    if item.get("status") not in STATUSES:
        error(f"unknown status '{item.get('status')}'")

    # 3. The source must be one of our feeds, and the link must be on that source's website
    source, url = item.get("source", ""), item.get("source_url", "")
    if source not in SOURCE_DOMAINS:
        error(f"unknown source '{source}'")
    elif not urlparse(url).netloc.removeprefix("www.").endswith(SOURCE_DOMAINS[source]):
        error(f"link is not on {SOURCE_DOMAINS[source]}: {url}")

    # 4. No duplicates
    if url in seen_urls:
        error("duplicate link (already published)")
    seen_urls.add(url)

    # 5. Date must be a real date and not in the future
    try:
        published = datetime.fromisoformat(item.get("published", ""))
        if published > datetime.now(timezone.utc):
            error("published date is in the future")
    except ValueError:
        error(f"published is not a valid date: '{item.get('published')}'")

    # 6. Style rules from the prompt
    text = " ".join(str(item.get(f, "")) for f in ("title", "summary", "why_it_matters")).lower()
    for word in HYPE_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", text):
            warn(f"hype word: '{word}'")
    n = count_sentences(item.get("summary", ""))
    if n > 3:
        warn(f"summary has {n} sentences (rule: 2-3)")
    n = count_sentences(item.get("why_it_matters", ""))
    if n > 2:
        warn(f"why_it_matters has {n} sentences (rule: 1-2)")
    if len(item.get("title", "")) > 100:
        warn(f"title is long ({len(item['title'])} characters)")

    # 7. Worth a human look: an outlet's story labeled "official"
    if source in NEWS_OUTLETS and item.get("status") == "official":
        warn("news-outlet story labeled 'official': check that the article quotes an official announcement")

    return problems


def main() -> int:
    items = json.loads(PUBLISHED_PATH.read_text())
    seen_urls: set = set()
    errors = warnings = 0
    flagged = 0

    for i, item in enumerate(items):
        problems = check_item(item, seen_urls)
        if not problems:
            continue
        flagged += 1
        print(f"\n#{i}  {item.get('title', '(no title)')}")
        for level, message in problems:
            print(f"    {level:5}  {message}")
            errors += level == "ERROR"
            warnings += level == "WARN"

    published = sum(1 for item in items if item.get("decision") == "publish")
    print("\n" + "-" * 60)
    print(f"Checked {published} published items: {published - flagged} clean, {flagged} flagged")
    print(f"{errors} errors, {warnings} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())