"""Then & Now: historical context for today's news.

Run with:  python app.py   then open http://localhost:5050
"""

from __future__ import annotations

import json
import logging
import os

import anthropic
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import audiences
from feeds import get_headlines
from historian import generate_context, generate_source_guide

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = Flask(__name__)

# Briefings already generated in this run, so re-opening a story is instant and free.
_briefings: dict = {}
_source_guides: dict = {}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.get("/")
def menu():
    return render_template("menu.html", audiences=audiences.AUDIENCES)


@app.get("/<any('11-13', '13-17', '18-plus'):audience>")
def reader(audience):
    return render_template("index.html", audience=audience, settings=audiences.get(audience))


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/headlines")
def headlines():
    force = request.args.get("refresh") == "1"
    audience = audiences.resolve(request.args.get("audience", ""))
    return jsonify(get_headlines(audience, force=force))


def _clean(body: dict, key: str, limit: int) -> str:
    return str(body.get(key, "")).strip()[:limit]


def _stream(generator_factory, cache: dict, cache_key, first_status: str, what: str) -> Response:
    """Stream a Claude job to the browser as server-sent events, caching the result."""

    def events():
        if cache_key in cache:
            yield _sse({"type": "result", "data": cache[cache_key]})
            return
        yield _sse({"type": "status", "message": first_status})
        try:
            for event in generator_factory():
                if event["type"] == "result":
                    cache[cache_key] = event["data"]
                yield _sse(event)
        except anthropic.AuthenticationError:
            yield _sse({"type": "error", "message": "Anthropic API key is missing or invalid. Set ANTHROPIC_API_KEY."})
        except anthropic.RateLimitError:
            yield _sse({"type": "error", "message": "Rate limited by the Anthropic API. Wait a minute and try again."})
        except anthropic.APIStatusError as exc:
            yield _sse({"type": "error", "message": f"Anthropic API error ({exc.status_code}): {exc.message}"})
        except anthropic.APIConnectionError:
            yield _sse({"type": "error", "message": "Couldn't reach the Anthropic API. Check your connection."})
        except Exception as exc:  # e.g. no credentials configured at all
            app.logger.exception("%s failed", what)
            message = str(exc)
            if "api_key" in message or "authentication" in message.lower():
                message = "No Anthropic API key found. Set ANTHROPIC_API_KEY and restart the app."
            yield _sse({"type": "error", "message": message or "Something went wrong."})

    return Response(
        stream_with_context(events()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _bad_url(url: str) -> bool:
    return bool(url) and not url.startswith(("http://", "https://"))


@app.post("/api/context")
def context():
    body = request.get_json(silent=True) or {}
    title = _clean(body, "title", 500)
    summary = _clean(body, "summary", 2000)
    url = _clean(body, "url", 2000)
    article_text = _clean(body, "text", 40000)
    audience = audiences.resolve(_clean(body, "audience", 20))

    if not title and not article_text:
        return jsonify({"error": "Provide a headline or the article text."}), 400
    if _bad_url(url):
        return jsonify({"error": "The URL must start with http:// or https://"}), 400
    if not title:
        title = article_text.split("\n", 1)[0][:200]

    return _stream(
        lambda: generate_context(title, summary, url, article_text, audience),
        _briefings,
        (audience, title, url, article_text),
        "Reading up on the story…",
        "Briefing",
    )


@app.post("/api/source")
def source_guide():
    body = request.get_json(silent=True) or {}
    title = _clean(body, "title", 500)
    url = _clean(body, "url", 2000)
    text = _clean(body, "text", 60000)
    story_title = _clean(body, "story_title", 500)
    audience = audiences.resolve(_clean(body, "audience", 20))

    if not url and not text:
        return jsonify({"error": "Provide a link to the source or paste its text."}), 400
    if _bad_url(url):
        return jsonify({"error": "The URL must start with http:// or https://"}), 400

    return _stream(
        lambda: generate_source_guide(title, url, text, story_title, audience),
        _source_guides,
        (audience, url, text),
        "Reading the source…",
        "Source guide",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    app.run(host="127.0.0.1", port=port, debug=True, threaded=True)
