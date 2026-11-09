"""Ask Claude for the historical context behind a news story.

Claude reads the article (web fetch), checks current facts (web search), and
then hands back its briefing by calling the `present_context` tool, whose
strict schema gives the web page a predictable structure to render.
"""

from __future__ import annotations

import os
from typing import Iterator, Optional

import anthropic

MODEL = os.environ.get("CONTEXT_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("CONTEXT_EFFORT", "medium")  # low | medium | high | xhigh | max
MAX_ROUNDS = 6

SYSTEM_PROMPT = """You are a historian who helps readers understand the news. Given a \
contemporary news story, explain the history a thoughtful reader needs to make sense of it: \
the long-run roots, the turning points that led here, relevant precedents and how they \
turned out, and the competing perspectives of the people involved.

Go back far enough. The most common failure is starting the story too recently, with only \
the last few years or the immediate trigger. Ask what a reader would need to know to \
understand why the people involved see the situation the way they do, and follow that back \
to its origin, even if it means decades or centuries. Collective memory of past events \
(invasions, coups, colonial rule, partitions, revolutions, broken agreements, past \
victories and humiliations) often explains present-day attitudes better than recent \
events do. For example, Iranian distrust of Western involvement makes little sense without \
the 1953 US- and UK-backed coup against Mossadegh, and that coup in turn makes more sense \
against the earlier history of foreign oil concessions and great-power rivalry in Iran. \
Work across time scales: the deep roots, the formative turning points, and the recent \
run-up to today's events.

How to work:
- If an article URL is provided, read it with web_fetch first. Use web_search to confirm \
recent developments, since the story may be newer than your training data.
- Keep the focus on history. Describe the current events only briefly, as the starting point.
- Be even-handed on contested topics: present each major perspective in terms its own \
holders would recognise, and separate established fact from interpretation.
- Be concrete: real dates, names, places and numbers. If you are unsure of a detail, say \
so rather than guessing.
- Only list sources you actually consulted or that are well-established references.

When you are finished, call the present_context tool exactly once with the full briefing. \
Do not write the briefing as plain text."""

PRESENT_CONTEXT_TOOL = {
    "name": "present_context",
    "description": "Deliver the finished historical-context briefing for the news story. "
    "Call this once, at the end, with every field filled in.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "story_title",
            "current_situation",
            "why_it_matters",
            "background",
            "timeline",
            "historical_parallels",
            "perspectives",
            "key_terms",
            "open_questions",
            "sources",
        ],
        "properties": {
            "story_title": {"type": "string", "description": "A short, neutral title for the story."},
            "current_situation": {
                "type": "string",
                "description": "2-3 sentences on what is happening now.",
            },
            "why_it_matters": {
                "type": "string",
                "description": "2-3 sentences on why the history matters for understanding this story.",
            },
            "background": {
                "type": "string",
                "description": "The historical narrative: 4-8 paragraphs separated by blank lines. "
                "Open with the deepest roots that still shape how the people involved see this "
                "story, then move through the formative turning points to the present.",
            },
            "timeline": {
                "type": "array",
                "description": "8-16 key moments in chronological order. Start at the deep roots "
                "described in the background, not just the recent run-up, so the timeline spans "
                "the full arc of the story.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["date", "event"],
                    "properties": {
                        "date": {"type": "string", "description": "Year or date, e.g. '1948' or 'March 2011'."},
                        "event": {"type": "string"},
                    },
                },
            },
            "historical_parallels": {
                "type": "array",
                "description": "1-3 earlier episodes that resemble this one.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "period", "similarities", "differences"],
                    "properties": {
                        "name": {"type": "string"},
                        "period": {"type": "string"},
                        "similarities": {"type": "string"},
                        "differences": {"type": "string"},
                    },
                },
            },
            "perspectives": {
                "type": "array",
                "description": "The main viewpoints of the parties involved.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["group", "view", "historical_memory"],
                    "properties": {
                        "group": {"type": "string"},
                        "view": {"type": "string"},
                        "historical_memory": {
                            "type": "string",
                            "description": "The past events this group remembers and draws on, and "
                            "how they shape its view today.",
                        },
                    },
                },
            },
            "key_terms": {
                "type": "array",
                "description": "People, places, organisations or concepts a reader may not know.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["term", "explanation"],
                    "properties": {"term": {"type": "string"}, "explanation": {"type": "string"}},
                },
            },
            "open_questions": {
                "type": "array",
                "description": "2-4 questions to watch as the story develops.",
                "items": {"type": "string"},
            },
            "sources": {
                "type": "array",
                "description": "Sources consulted, with URLs.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "url"],
                    "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                },
            },
        },
    },
}

TOOLS = [
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 3},
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 6},
    PRESENT_CONTEXT_TOOL,
]

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _build_request(title: str, summary: str, url: str, article_text: str) -> str:
    parts = ["Give me the historical context for this news story.", "", f"Headline: {title}"]
    if summary:
        parts.append(f"Summary: {summary}")
    if url:
        parts.append(f"Article URL: {url}")
    if article_text:
        parts += ["", "Article text:", "<article>", article_text, "</article>"]
    return "\n".join(parts)


def _describe_tool_call(block) -> Optional[str]:
    tool_input = block.input if isinstance(block.input, dict) else {}
    if block.name == "web_search" and tool_input.get("query"):
        return f"Searching: {tool_input['query']}"
    if block.name == "web_fetch" and tool_input.get("url"):
        return f"Reading: {tool_input['url']}"
    return None


def generate_context(
    title: str, summary: str = "", url: str = "", article_text: str = ""
) -> Iterator[dict]:
    """Yield progress events, ending with {"type": "result"} or {"type": "error"}."""
    client = _get_client()
    messages: list = [{"role": "user", "content": _build_request(title, summary, url, article_text)}]

    for _ in range(MAX_ROUNDS):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": EFFORT},
            # If a safety classifier declines, retry on Anthropic's recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            for event in stream:
                if event.type == "content_block_stop":
                    block = stream.current_message_snapshot.content[event.index]
                    if block.type == "server_tool_use":
                        note = _describe_tool_call(block)
                        if note:
                            yield {"type": "status", "message": note}
            message = stream.get_final_message()

        if message.stop_reason == "refusal":
            yield {"type": "error", "message": "Claude declined to provide context for this story."}
            return
        if message.stop_reason == "max_tokens":
            yield {"type": "error", "message": "The response was too long and got cut off. Please try again."}
            return

        for block in message.content:
            if block.type == "tool_use" and block.name == "present_context":
                yield {"type": "result", "context": block.input}
                return

        # Server tools paused mid-turn, or Claude answered in prose: continue the same turn.
        messages.append({"role": "assistant", "content": message.content})
        if message.stop_reason != "pause_turn":
            messages.append(
                {"role": "user", "content": "Please deliver the briefing by calling the present_context tool."}
            )
        yield {"type": "status", "message": "Writing the briefing…"}

    yield {"type": "error", "message": "Claude did not finish the briefing. Please try again."}
