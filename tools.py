from datetime import datetime, timedelta, timezone
# pyrefly: ignore [missing-import]
import feedparser
# pyrefly: ignore [missing-import]
import trafilatura
import json
from pathlib import Path
import re


FEEDS = {
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "Ars Technica": "https://arstechnica.com/ai/feed/",
}

_FEED_SUMMARIES = {}   # link -> short summary from the RSS feed

def _clean_url(url: str) -> str:
    return url.strip().rstrip("/")

def get_latest_items(days: int = 7, max_items: int = 20) -> list[dict]:
    """Return recent items from all feeds, newest first."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items = []
    for source, url in FEEDS.items():
        feed = feedparser.parse(url)
        print(f"{source}: {len(feed.entries)} entries")
        for entry in feed.entries:
            parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            if not parsed:
                continue
            published = datetime(*parsed[:6], tzinfo=timezone.utc)
            if published < cutoff:
                continue
            summary = re.sub(r"<[^>]+>", " ", entry.get("summary", "")).strip()
            _FEED_SUMMARIES[_clean_url(entry.get("link", ""))] = summary[:1000]
            items.append({
                "source": source,
                "author": entry.get("author", ""),
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": published.isoformat(),
            })
    items.sort(key=lambda item: item["published"], reverse=True)
    return items[:max_items]


def fetch_article(url: str, max_chars: int = 5000) -> str:
    """Download a page and return the main article text."""
    downloaded = trafilatura.fetch_url(url)
    text = trafilatura.extract(downloaded) if downloaded else ""
    if text:
        return text[:max_chars]

    summary = _FEED_SUMMARIES.get(_clean_url(url), "")
    if summary:
        return ("[The full article could not be downloaded. "
                "Only the short summary from the news feed is available:]\n" + summary)
    return "[The article could not be downloaded, and no feed summary is available.]"

PUBLISHED_PATH = Path(__file__).parent / "published.json"

def _load_published() -> list[dict]:
    if not PUBLISHED_PATH.exists():
        return []
    return json.loads(PUBLISHED_PATH.read_text())

def is_published(url: str) -> bool:
    """Check whether an item with this link is already on the website."""
    return any(item.get("source_url") == url for item in _load_published())

def save_item(item: dict) -> str:
    """Save a finished news item for the website."""
    items = _load_published()
    if any(saved.get("source_url") == item.get("source_url") for saved in items):
        return "Already saved."
    items.append(item)
    PUBLISHED_PATH.write_text(json.dumps(items, indent=2, ensure_ascii=False))
    return f"Saved: {item.get('title')}"

def get_recent_published(limit: int = 50) -> list[dict]:
    """Return the titles and links of the most recent items on the website."""
    items = _load_published()
    return [
        {"title": item.get("title"), "source_url": item.get("source_url")}
        for item in items[-limit:]
    ]


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_latest_items",
            "description": "Get recent headlines from the AI news sources, newest first. Each item has source, title, link and published date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "How many days back to look. Default 2."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_published",
            "description": "Get the titles and links of the items already on the website, to avoid duplicates.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_article",
            "description": "Download an article and return its main text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The article link."}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_item",
            "description": "Save one finished news item to the website. Use the ITEM FORMAT from your instructions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "object", "description": "The finished news item."}
                },
                "required": ["item"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "get_latest_items": get_latest_items,
    "get_recent_published": get_recent_published,
    "fetch_article": fetch_article,
    "save_item": save_item,
}

if __name__ == "__main__":
    items = get_latest_items(days=7)
    for item in items:
        print(f"{item['published'][:10]}  [{item['source']}]  {item['title']}")

    print("\n--- First article ---\n")
    print(fetch_article(items[0]["link"])[:1000])