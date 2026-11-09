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

Tell the history from more than one side. English-language news and popular history often \
default to the viewpoint of Western governments, and their framing can quietly become the \
narrator's voice. Avoid that. Tell events as they were experienced by the people they \
happened to, as well as by the powers that acted on them, and don't adopt any one \
government's description as neutral fact. For example, Western accounts often say US \
forces "liberated" Korea in 1945. But the US Army Military Government then governed the \
south for three years, kept many Japanese-era officials and police in place, and set aside \
the Korean People's Republic that Koreans had formed themselves, so many Koreans experienced \
it as a new occupation. Where descriptions like this are contested, say who uses which \
account and why, instead of choosing one. Apply the same scrutiny to every power involved, \
Western or not.

How to work:
- If an article URL is provided, read it with web_fetch first. Use web_search to confirm \
recent developments, since the story may be newer than your training data.
- Ground the history in scholarship, not just news coverage: search for academic work \
(journal articles, university press books, university and research-institute pages) and \
look especially for historians and writers from the countries and communities involved. \
Where they help, include primary sources and first-hand accounts from the people affected.
- Read every source critically: consider who produced it, when, for whom and why, and \
check its claims against other sources before relying on it.
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
            "contested_accounts",
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
                "description": "The main viewpoints, including the ordinary people and communities "
                "the history happened to, not only governments and officials.",
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
            "contested_accounts": {
                "type": "array",
                "description": "1-4 events in this history that different groups describe in "
                "conflicting ways (for example 'liberation' versus 'occupation').",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["event", "accounts"],
                    "properties": {
                        "event": {"type": "string"},
                        "accounts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["held_by", "account"],
                                "properties": {
                                    "held_by": {"type": "string", "description": "Who tells it this way."},
                                    "account": {"type": "string", "description": "How they describe it, and why."},
                                },
                            },
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
                "description": "Sources consulted, with URLs. Include academic work where possible.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "url", "kind"],
                    "properties": {
                        "title": {"type": "string", "description": "Title, with author where known."},
                        "url": {"type": "string"},
                        "kind": {"type": "string", "enum": ["academic", "primary", "news", "reference"]},
                    },
                },
            },
        },
    },
}

TOOLS = [
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 6},
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 10},
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




# ---------------------------------------------------------------------------
# Source reading guides: help readers understand a historical source.
# ---------------------------------------------------------------------------

SOURCE_SYSTEM_PROMPT = """You are a historian who teaches people to read historical sources \
critically. Given a source (a document, speech, treaty, letter, article, book or web page), \
write a reading guide that helps a general reader understand it the way a historian would.

Use the historian's core methods:
- Sourcing: who produced it, when, where, for what audience and for what purpose.
- Contextualisation: what was happening at the time, and what the author could and couldn't know.
- Close reading: what it actually says, in plain modern language, including its word choices and tone.
- Perspective: whose viewpoint it represents, what it emphasises or leaves out, and whose voices are missing.
- Corroboration: how it fits with, or contradicts, other evidence and the accounts of other groups involved.

How to work:
- If a URL is given, read the source with web_fetch. Use web_search to find out about the \
author, the circumstances of its production, and how historians, including historians from \
the communities it describes, have interpreted it.
- Apply the same scrutiny to every source, whoever produced it. Official and Western sources \
are not neutral by default.
- Keep quotations short (under 25 words each) and only quote what you need to explain.
- If you can't read the source itself, say so plainly in the summary and base the guide on \
what you can establish about it.

When you are finished, call the present_source_guide tool exactly once. Do not write the \
guide as plain text."""


def _obj(properties: dict, **extra) -> dict:
    """A strict JSON-schema object: every property required, no extras."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
        **extra,
    }


_TEXT = {"type": "string"}

PRESENT_SOURCE_GUIDE_TOOL = {
    "name": "present_source_guide",
    "description": "Deliver the finished reading guide for the historical source. "
    "Call this once, at the end, with every field filled in.",
    "strict": True,
    "input_schema": _obj(
        {
            "title": {"type": "string", "description": "The source's title."},
            "author": {"type": "string", "description": "Who produced it, or 'Unknown'."},
            "date": {"type": "string", "description": "When it was produced, as precisely as known."},
            "source_type": {
                "type": "string",
                "enum": ["primary", "secondary", "tertiary"],
                "description": "Primary: produced at the time by participants or witnesses. "
                "Secondary: later analysis. Tertiary: summaries such as encyclopaedias.",
            },
            "plain_summary": {"type": "string", "description": "What it says, in 2-4 plain sentences."},
            "context": {"type": "string", "description": "What was happening when it was produced."},
            "author_and_purpose": {
                "type": "string",
                "description": "Who the author was, their position, intended audience and purpose.",
            },
            "perspective": {
                "type": "string",
                "description": "Whose viewpoint it represents, what it emphasises or omits, "
                "and whose voices are missing.",
            },
            "key_passages": {
                "type": "array",
                "description": "2-5 important short passages and what they mean.",
                "items": _obj({"passage": {"type": "string", "description": "Under 25 words."}, "meaning": _TEXT}),
            },
            "difficult_terms": {
                "type": "array",
                "description": "Archaic, technical or loaded words a modern reader may misread.",
                "items": _obj({"term": _TEXT, "explanation": _TEXT}),
            },
            "reliability": {
                "type": "string",
                "description": "What this source is and isn't good evidence for, and how it "
                "fits with other evidence.",
            },
            "other_viewpoints": {
                "type": "array",
                "description": "How other groups involved saw the same events.",
                "items": _obj({"group": _TEXT, "view": _TEXT}),
            },
            "questions_to_ask": {
                "type": "array",
                "description": "2-4 questions a reader should keep in mind.",
                "items": _TEXT,
            },
            "further_reading": {
                "type": "array",
                "description": "Sources that help interpret this one, ideally academic.",
                "items": _obj({"title": _TEXT, "url": _TEXT}),
            },
        }
    ),
}

SOURCE_TOOLS = [
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 4},
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 6},
    PRESENT_SOURCE_GUIDE_TOOL,
]


def _build_source_request(title: str, url: str, text: str, story_title: str) -> str:
    parts = ["Write a reading guide for this historical source."]
    if title:
        parts.append(f"Title: {title}")
    if url:
        parts.append(f"URL: {url}")
    if story_title:
        parts.append(f"The reader found it while reading about: {story_title}")
    if text:
        parts += ["", "Source text:", "<source>", text, "</source>"]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Shared request loop
# ---------------------------------------------------------------------------


def _run(system: str, tools: list, result_tool: str, request: str, what: str) -> Iterator[dict]:
    """Run Claude until it calls `result_tool`; yield status events, then a result or error."""
    client = _get_client()
    messages: list = [{"role": "user", "content": request}]

    for _ in range(MAX_ROUNDS):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=system,
            tools=tools,
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
            yield {"type": "error", "message": f"Claude declined to write the {what}."}
            return
        if message.stop_reason == "max_tokens":
            yield {"type": "error", "message": "The response was too long and got cut off. Please try again."}
            return

        for block in message.content:
            if block.type == "tool_use" and block.name == result_tool:
                yield {"type": "result", "data": block.input}
                return

        # Server tools paused mid-turn, or Claude answered in prose: continue the same turn.
        messages.append({"role": "assistant", "content": message.content})
        if message.stop_reason != "pause_turn":
            messages.append({"role": "user", "content": f"Please deliver the {what} by calling the {result_tool} tool."})
        yield {"type": "status", "message": f"Writing the {what}…"}

    yield {"type": "error", "message": f"Claude did not finish the {what}. Please try again."}


def generate_context(
    title: str, summary: str = "", url: str = "", article_text: str = ""
) -> Iterator[dict]:
    """Historical-context briefing for a news story."""
    request = _build_request(title, summary, url, article_text)
    return _run(SYSTEM_PROMPT, TOOLS, "present_context", request, "briefing")


def generate_source_guide(
    title: str = "", url: str = "", text: str = "", story_title: str = ""
) -> Iterator[dict]:
    """Reading guide that explains a historical source critically."""
    request = _build_source_request(title, url, text, story_title)
    return _run(SOURCE_SYSTEM_PROMPT, SOURCE_TOOLS, "present_source_guide", request, "reading guide")
