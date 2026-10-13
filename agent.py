"""The news agent, in two stages.

1. Choose: one call. The model sees the numbered headlines and what is already
   published, and picks the stories worth covering.
2. Write: for each chosen story, a fresh, small conversation with two tools
   (fetch_article and save_item). Each story starts with an empty context,
   so nothing has to be trimmed and nothing gets fetched twice.

Run:  python agent.py
"""
import json
import os
import re
from datetime import date

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from groq import BadRequestError, Groq

from build_site import build
from prompt import CHOOSER_PROMPT, SYSTEM_PROMPT
from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, get_latest_items, get_recent_published

MAX_STORIES = 5            # at most this many stories per run
MAX_STEPS_PER_STORY = 6    # fetch, save, final sentence, plus room for one retry
MAX_BAD_CALLS = 3          # invalid tool calls tolerated per conversation
HEADLINE_DAYS = 2         # how far back to look for headlines

# The writer only needs these two tools
WRITER_TOOLS = [schema for schema in TOOL_SCHEMAS
                if schema["function"]["name"] in ("fetch_article", "save_item")]


def parse_json(text: str) -> dict:
    """Find the JSON object in a model reply (models sometimes add ``` fences)."""
    clean = re.sub(r"```(?:json)?", "", text or "").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def run_loop(client, model: str, messages: list[dict], tools: list[dict] | None,
             max_steps: int, label: str) -> str:
    """A small agent loop. Returns the model's final text reply."""
    bad_calls = 0
    for step in range(1, max_steps + 1):
        request = {"model": model, "messages": messages, "temperature": 0.3}
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"

        try:
            response = client.chat.completions.create(**request)
        except BadRequestError:
            # The model produced a tool call that isn't valid JSON
            bad_calls += 1
            print(f"  [{label}] invalid tool call ({bad_calls}/{MAX_BAD_CALLS})")
            if bad_calls >= MAX_BAD_CALLS:
                return ""
            messages.append({"role": "user", "content":
                             "Your last tool call was not valid. Try again with a valid tool call."})
            continue

        message = response.choices[0].message

        # No tool calls means the model is done
        if not message.tool_calls:
            return message.content or ""

        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [call.model_dump() for call in message.tool_calls],
        })

        for call in message.tool_calls:
            name = call.function.name
            args = {}
            try:
                args = json.loads(call.function.arguments or "{}")
                result = TOOL_FUNCTIONS[name](**args)
            except Exception as e:
                result = f"Error: {e}"
            print(f"  [{label} step {step}] {name}({str(args)[:70]})")
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    print(f"  [{label}] stopped: reached the maximum number of steps.")
    return ""


def choose_stories(client, model: str, today: str) -> list[dict]:
    """Stage 1: the model picks which headlines to cover, by number."""
    headlines = get_latest_items(days=HEADLINE_DAYS)
    if not headlines:
        print("No new headlines.")
        return []

    published = get_recent_published()
    numbered = "\n".join(
        f"{i}. [{item['source']}] {item['title']} ({item['published'][:10]})"
        for i, item in enumerate(headlines, 1)
    )
    already = "\n".join(f"- {item['title']}" for item in published) or "(nothing yet)"

    messages = [
        {"role": "system", "content": CHOOSER_PROMPT},
        {"role": "user", "content": f"Today is {today}.\n\nHEADLINES:\n{numbered}\n\nALREADY ON THE WEBSITE:\n{already}"},
    ]
    plan = parse_json(run_loop(client, model, messages, tools=None, max_steps=1, label="choose"))

    for skipped in plan.get("skipped", []):
        print(f"  skipped #{skipped.get('number')}: {skipped.get('reason')}")

    chosen = []
    for number in plan.get("chosen", [])[:MAX_STORIES]:
        if isinstance(number, int) and 1 <= number <= len(headlines):
            chosen.append(headlines[number - 1])
    return chosen


def write_story(client, model: str, today: str, item: dict):
    """Stage 2: a fresh, small conversation for one story."""
    task = (
        f"Today is {today}. Write the website item for this story.\n\n"
        f"Headline: {item['title']}\n"
        f"Source: {item['source']}\n"
        f"Author: {item.get('author') or 'unknown'}\n"
        f"Date: {item['published']}\n"
        f"Link: {item['link']}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    reply = run_loop(client, model, messages, WRITER_TOOLS, MAX_STEPS_PER_STORY, label="write")
    print(f"  -> {reply.strip()[:200] or '(no final reply)'}")


def run_agent():
    load_dotenv(override=True)
    client = Groq(api_key=os.environ["GROQ_API_KEY"].strip(), max_retries=5)
    model = os.environ["GROQ_MODEL"].strip().strip('"')
    today = date.today().isoformat()

    try:
        print("== Stage 1: choosing stories ==")
        chosen = choose_stories(client, model, today)
        print(f"Chosen: {len(chosen)} stories")

        for i, item in enumerate(chosen, 1):
            print(f"\n== Stage 2: story {i}/{len(chosen)}: {item['title']} ==")
            write_story(client, model, today, item)
    finally:
        build()   # runs however the agent ends: finished, stopped, or crashed


if __name__ == "__main__":
    run_agent()