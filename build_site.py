"""Build the website (docs/index.html) from published.json.

The page is plain HTML, so every story is readable even without JavaScript.
A small script on top adds three things:
  - filter chips, to show one category at a time
  - "Show more", so the page starts short instead of listing every story
  - hiding the date headings that have no stories left after filtering

Run:  python build_site.py
"""
import html
import json
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
PUBLISHED_PATH = ROOT / "published.json"
OUTPUT_PATH = ROOT / "docs" / "index.html"

# Order of the filter chips, and the color that marks each category
CATEGORIES = {
    "New models": "#2563eb",
    "Research": "#7c3aed",
    "Tools and products": "#0f766e",
    "Industry and funding": "#c2410c",
    "Policy and safety": "#64748b",
}

LATEST_COUNT = 5   # stories in the "Latest" column next to the lead story
PAGE_SIZE = 12     # stories shown before (and added by) the "Show more" button

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI News, Explained Simply</title>
<meta name="description" content="The important AI news, explained in plain English for people who can't keep up.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600;6..72,700&family=Geist:wght@400;500;600&display=swap" rel="stylesheet">
<script>document.documentElement.classList.add("js");</script>
<style>
  :root {
    --paper: #ffffff; --ink: #14161a; --muted: #5b616e; --rule: #e2e4e8;
    --link: #1d4ed8; --soft: #f4f5f7; --card: #ffffff;
    --serif: "Newsreader", Georgia, serif;
    --sans: "Geist", ui-sans-serif, system-ui, sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root { --paper: #121418; --ink: #eceef1; --muted: #9aa1ad; --rule: #2a2e35;
            --link: #8fb2ff; --soft: #1b1e24; --card: #171a1f; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--paper); color: var(--ink); font-family: var(--sans);
         font-size: 16px; line-height: 1.55; -webkit-font-smoothing: antialiased; }
  a { color: inherit; text-decoration: none; }
  .wrap { max-width: 1120px; margin: 0 auto; padding: 0 24px; }
  @media (max-width: 520px) { .wrap { padding: 0 16px; } }

  /* masthead */
  .masthead { border-bottom: 1px solid var(--rule); }
  .masthead .wrap { display: flex; flex-wrap: wrap; align-items: baseline;
                    justify-content: space-between; gap: 8px 24px; padding-top: 28px; padding-bottom: 18px; }
  .brand { font-family: var(--serif); font-weight: 700; font-size: clamp(1.9rem, 4vw, 2.8rem);
           letter-spacing: -0.02em; line-height: 1; margin: 0; }
  .tagline { color: var(--muted); font-size: .95rem; margin: 0; }

  /* filter bar: stays at the top while scrolling */
  .filters { position: sticky; top: 0; z-index: 10; background: var(--paper);
             border-bottom: 1px solid var(--rule); }
  .filters .wrap { display: flex; gap: 8px; overflow-x: auto; padding-top: 10px; padding-bottom: 10px;
                   scrollbar-width: none; }
  .filters .wrap::-webkit-scrollbar { display: none; }
  .chip { flex-shrink: 0; display: inline-flex; align-items: center; gap: 8px; cursor: pointer;
          font: 500 .88rem var(--sans); color: var(--muted); background: transparent;
          border: 1px solid var(--rule); border-radius: 999px; padding: 6px 14px; white-space: nowrap; }
  .chip:hover { color: var(--ink); border-color: var(--muted); }
  .chip[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .chip .count { font-size: .78rem; opacity: .7; }
  html:not(.js) .filters { display: none; }
  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex-shrink: 0; }

  /* top: lead story + latest column */
  .top { display: grid; grid-template-columns: 1fr; gap: 36px; padding: 36px 0 44px;
         border-bottom: 1px solid var(--rule); }
  @media (min-width: 860px) { .top { grid-template-columns: 2fr 1fr; gap: 48px; } }
  .kicker { display: inline-flex; align-items: center; gap: 8px; font-size: .82rem; font-weight: 600; }
  .lead h2 { font-family: var(--serif); font-weight: 700; font-size: clamp(2rem, 4.6vw, 3.3rem);
             line-height: 1.08; letter-spacing: -0.02em; margin: 14px 0 18px; max-width: 22ch; }
  .lead h2 a:hover { color: var(--link); }
  .lead .summary { font-family: var(--serif); font-size: 1.25rem; line-height: 1.5; margin: 0 0 18px; max-width: 38em; }
  .why { background: var(--soft); border-left: 3px solid var(--accent, var(--muted));
         padding: 12px 16px; margin: 0 0 18px; max-width: 38em; }
  .why strong { font-weight: 600; }
  .byline { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; color: var(--muted); font-size: .86rem; }
  .byline .source { color: var(--ink); font-weight: 500; }
  .read { color: var(--link); font-weight: 500; }
  .read:hover { text-decoration: underline; }

  .latest h3 { font-size: 1rem; font-weight: 600; margin: 0 0 6px; padding-bottom: 10px; border-bottom: 2px solid var(--ink); }
  .latest ol { list-style: none; margin: 0; padding: 0; }
  .latest li { padding: 14px 0; border-bottom: 1px solid var(--rule); }
  .latest li a { font-family: var(--serif); font-size: 1.12rem; font-weight: 600; line-height: 1.3; display: block; margin: 6px 0; }
  .latest li a:hover { color: var(--link); }
  .small { font-size: .8rem; color: var(--muted); display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }

  /* status labels: how confirmed the news is */
  .status { font-size: .72rem; font-weight: 500; padding: 1px 8px; border-radius: 4px; }
  .status.official { background: var(--ink); color: var(--paper); }
  .status.reported { border: 1px solid var(--muted); color: var(--muted); }
  .status.rumor { border: 1px dashed #b45309; color: #b45309; }

  /* the feed: stories grouped by day, as a grid of compact cards */
  .feed { padding: 8px 0 24px; }
  .day h2 { font-size: .8rem; font-weight: 600; text-transform: uppercase; letter-spacing: .08em;
            color: var(--muted); margin: 32px 0 14px; display: flex; align-items: center; gap: 12px; }
  .day h2::after { content: ""; flex: 1; height: 1px; background: var(--rule); }
  .grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
  @media (min-width: 700px) { .grid { grid-template-columns: repeat(2, 1fr); } }
  @media (min-width: 1000px) { .grid { grid-template-columns: repeat(3, 1fr); } }

  .card { background: var(--card); border: 1px solid var(--rule); border-top: 3px solid var(--color);
          border-radius: 8px; padding: 14px 16px 12px; display: flex; flex-direction: column; gap: 8px; }
  .card h3 { font-family: var(--serif); font-size: 1.18rem; font-weight: 600; line-height: 1.25; margin: 0; }
  .card h3 a:hover { color: var(--link); }
  .card .gist { margin: 0; color: var(--muted); font-size: .93rem;
                display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .card details { font-size: .93rem; }
  .card summary { cursor: pointer; color: var(--link); font-weight: 500; font-size: .85rem; list-style: none; }
  .card summary::-webkit-details-marker { display: none; }
  .card summary::before { content: "+ "; }
  .card details[open] summary::before { content: "− "; }
  .card details p { margin: 8px 0 0; }
  .card .byline { margin-top: auto; padding-top: 8px; border-top: 1px solid var(--rule); font-size: .8rem; }
  .card .byline .read { margin-left: auto; }

  /* hidden by the filter or by "show more" (only when JavaScript runs) */
  .js .is-hidden { display: none !important; }

  .more-row { text-align: center; padding: 8px 0 40px; }
  .more { font: 500 .92rem var(--sans); color: var(--ink); background: var(--soft); cursor: pointer;
          border: 1px solid var(--rule); border-radius: 999px; padding: 10px 22px; }
  .more:hover { border-color: var(--muted); }
  html:not(.js) .more-row { display: none; }
  .empty { color: var(--muted); padding: 32px 0; }

  footer { border-top: 1px solid var(--rule); padding: 36px 0 56px; color: var(--muted); font-size: .9rem; }
  footer p { max-width: 42em; margin: 0 0 8px; }

  a:focus-visible, button:focus-visible, summary:focus-visible { outline: 2px solid var(--link); outline-offset: 3px; border-radius: 4px; }
</style>
</head>
<body>
<header class="masthead">
  <div class="wrap">
    <h1 class="brand">AI News, Explained Simply</h1>
    <p class="tagline">The important AI news in plain English. Updated {{updated}}.</p>
  </div>
</header>
<nav class="filters" aria-label="Filter by category"><div class="wrap">{{chips}}</div></nav>
<main class="wrap">
  {{top}}
  <div class="feed" id="feed">{{feed}}</div>
  <p class="empty is-hidden" id="empty">No stories in this category yet.</p>
  <div class="more-row"><button class="more" id="more" type="button">Show more stories</button></div>
</main>
<footer>
  <div class="wrap">
    <p>Stories are found and summarized by an AI agent from official company blogs and news sites, then checked against the source. Every story links to its original article.</p>
    <p><strong>Official</strong> means the company announced it. <strong>Reported</strong> means a news outlet reported it. <strong>Rumor</strong> means it is not confirmed.</p>
  </div>
</footer>
<script>
(function () {
  var PAGE = {{page_size}};
  var shown = PAGE;
  var current = "all";
  var top = document.getElementById("top");
  var cards = Array.prototype.slice.call(document.querySelectorAll(".card"));
  var days = Array.prototype.slice.call(document.querySelectorAll(".day"));
  var chips = Array.prototype.slice.call(document.querySelectorAll(".chip"));
  var more = document.getElementById("more");
  var empty = document.getElementById("empty");

  function render() {
    // "All": the top block shows the newest stories, so the feed skips them.
    // One category: hide the top block and show every story in that category.
    var matching = cards.filter(function (card) {
      if (current === "all") return card.dataset.top !== "1";
      return card.dataset.category === current;
    });
    cards.forEach(function (card) { card.classList.add("is-hidden"); });
    matching.slice(0, shown).forEach(function (card) { card.classList.remove("is-hidden"); });

    days.forEach(function (day) {
      day.classList.toggle("is-hidden", !day.querySelector(".card:not(.is-hidden)"));
    });
    if (top) top.classList.toggle("is-hidden", current !== "all");

    var left = matching.length - shown;
    more.parentNode.classList.toggle("is-hidden", left <= 0);
    more.textContent = "Show more stories (" + left + " left)";
    empty.classList.toggle("is-hidden", matching.length > 0);
  }

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      current = chip.dataset.filter;
      shown = PAGE;
      chips.forEach(function (c) { c.setAttribute("aria-pressed", String(c === chip)); });
      render();
    });
  });
  more.addEventListener("click", function () { shown += PAGE; render(); });
  render();
})();
</script>
</body>
</html>
"""

e = html.escape


def load_items() -> list[dict]:
    """Read published.json, keep only published items, newest first."""
    if not PUBLISHED_PATH.exists():
        return []
    items = json.loads(PUBLISHED_PATH.read_text())
    items = [item for item in items if item.get("decision") == "publish"]
    items.sort(key=lambda item: item.get("published", ""), reverse=True)
    return items


def parse_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value).date()
    except (ValueError, TypeError):
        return None


def nice_date(value: str) -> str:
    """'2026-10-02T15:00:00+00:00' -> '2 Oct 2026'."""
    day = parse_date(value)
    return day.strftime("%-d %b %Y") if day else ""


def day_heading(day: date | None, today: date) -> str:
    """Heading for a group of stories: 'Today', 'Yesterday', or 'Monday 12 October'."""
    if day is None:
        return "Earlier"
    gap = (today - day).days
    if gap == 0:
        return "Today"
    if gap == 1:
        return "Yesterday"
    return day.strftime("%A %-d %B")


def color_of(item: dict) -> str:
    return CATEGORIES.get(item.get("category", ""), "#6b7280")


def kicker(item: dict) -> str:
    """Colored dot + category name."""
    return (f'<span class="kicker"><span class="dot" style="background:{color_of(item)}"></span>'
            f'{e(item.get("category", ""))}</span>')


def status_label(item: dict) -> str:
    status = item.get("status", "")
    if status not in ("official", "reported", "rumor"):
        return ""
    return f'<span class="status {status}">{status.capitalize()}</span>'


def link(item: dict, text: str, css: str = "") -> str:
    class_attr = f' class="{css}"' if css else ""
    return (f'<a{class_attr} href="{e(item.get("source_url", ""))}" target="_blank" rel="noopener">'
            f'{text}</a>')


def render_lead(item: dict) -> str:
    why = item.get("why_it_matters", "")
    why_html = (f'<p class="why" style="--accent:{color_of(item)}"><strong>Why it matters:</strong> {e(why)}</p>'
                if why else "")
    return f"""
    <article class="lead">
      <div class="small">{kicker(item)}{status_label(item)}</div>
      <h2>{link(item, e(item.get("title", "")))}</h2>
      <p class="summary">{e(item.get("summary", ""))}</p>
      {why_html}
      <div class="byline"><span class="source">{e(item.get("source", ""))}</span>
        <span>{nice_date(item.get("published", ""))}</span>
        {link(item, "Read the original article", "read")}</div>
    </article>"""


def render_latest(items: list[dict]) -> str:
    if not items:
        return ""
    rows = "".join(
        f'<li><span class="small">{kicker(item)}</span>'
        f'{link(item, e(item.get("title", "")))}'
        f'<span class="small">{e(item.get("source", ""))} · {nice_date(item.get("published", ""))}</span></li>'
        for item in items
    )
    return f'<aside class="latest" aria-label="Latest stories"><h3>Latest</h3><ol>{rows}</ol></aside>'


def render_card(item: dict, in_top: bool) -> str:
    """A compact card: headline and why it matters; the full summary opens on tap."""
    why = item.get("why_it_matters", "")
    summary = item.get("summary", "")
    gist = f'<p class="gist">{e(why or summary)}</p>' if (why or summary) else ""
    details = (f'<details><summary>Full summary</summary><p>{e(summary)}</p></details>'
               if why and summary else "")
    return f"""
        <article class="card" style="--color:{color_of(item)}"
                 data-category="{e(item.get("category", ""))}" data-top="{1 if in_top else 0}">
          <div class="small">{kicker(item)}{status_label(item)}</div>
          <h3>{link(item, e(item.get("title", "")))}</h3>
          {gist}
          {details}
          <div class="byline"><span class="source">{e(item.get("source", ""))}</span>
            <span>{nice_date(item.get("published", ""))}</span>
            {link(item, "Read →", "read")}</div>
        </article>"""


def render_feed(items: list[dict], top_count: int, today: date) -> str:
    """Every story, grouped by the day it was published, newest first."""
    groups: list[tuple[str, list[str]]] = []
    for index, item in enumerate(items):
        heading = day_heading(parse_date(item.get("published", "")), today)
        if not groups or groups[-1][0] != heading:
            groups.append((heading, []))
        groups[-1][1].append(render_card(item, in_top=index < top_count))
    return "".join(
        f'<section class="day"><h2>{e(heading)}</h2><div class="grid">{"".join(cards)}</div></section>'
        for heading, cards in groups
    )


def render_chips(items: list[dict]) -> str:
    chips = [f'<button class="chip" type="button" data-filter="all" aria-pressed="true">'
             f'All <span class="count">{len(items)}</span></button>']
    for category, color in CATEGORIES.items():
        count = sum(1 for item in items if item.get("category") == category)
        if count:
            chips.append(
                f'<button class="chip" type="button" data-filter="{e(category)}" aria-pressed="false">'
                f'<span class="dot" style="background:{color}"></span>{e(category)} '
                f'<span class="count">{count}</span></button>')
    return "".join(chips)


def build():
    items = load_items()
    now = datetime.now(timezone.utc)

    if items:
        lead, latest = items[0], items[1:1 + LATEST_COUNT]
        top = f'<div class="top" id="top">{render_lead(lead)}{render_latest(latest)}</div>'
        top_count = 1 + len(latest)
    else:
        top = '<div class="top" id="top"><p>No stories yet. Run the agent to add the first ones.</p></div>'
        top_count = 0

    page = (TEMPLATE
            .replace("{{updated}}", now.strftime("%A %-d %B %Y"))
            .replace("{{chips}}", render_chips(items))
            .replace("{{top}}", top)
            .replace("{{feed}}", render_feed(items, top_count, now.date()))
            .replace("{{page_size}}", str(PAGE_SIZE)))

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(page, encoding="utf-8")
    print(f"Built {OUTPUT_PATH} with {len(items)} stories.")


if __name__ == "__main__":
    build()