"""Then & Now: historical context for today's news.

Run with:  python app.py   then open http://localhost:5050
"""

from __future__ import annotations

import json
import os

import anthropic
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from feeds import get_headlines
from historian import generate_context

app = Flask(__name__)

# Briefings already generated in this run, so re-opening a story is instant and free.
_briefings: dict = {}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/headlines")
def headlines():
    force = request.args.get("refresh") == "1"
    return jsonify(get_headlines(force=force))


@app.post("/api/context")
def context():
    body = request.get_json(silent=True) or {}
    title = str(body.get("title", "")).strip()[:500]
    summary = str(body.get("summary", "")).strip()[:2000]
    url = str(body.get("url", "")).strip()[:2000]
    article_text = str(body.get("text", "")).strip()[:40000]

    if not title and not article_text:
        return jsonify({"error": "Provide a headline or the article text."}), 400
    if url and not url.startswith(("http://", "https://")):
        return jsonify({"error": "The URL must start with http:// or https://"}), 400
    if not title:
        title = article_text.split("\n", 1)[0][:200]

    cache_key = (title, url, article_text)

    def events():
        if cache_key in _briefings:
            yield _sse({"type": "result", "context": _briefings[cache_key]})
            return
        yield _sse({"type": "status", "message": "Reading up on the story…"})
        try:
            for event in generate_context(title, summary, url, article_text):
                if event["type"] == "result":
                    _briefings[cache_key] = event["context"]
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
            app.logger.exception("Briefing failed")
            message = str(exc)
            if "api_key" in message or "authentication" in message.lower():
                message = "No Anthropic API key found. Set ANTHROPIC_API_KEY and restart the app."
            yield _sse({"type": "error", "message": message or "Something went wrong."})

    return Response(
        stream_with_context(events()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    app.run(host="127.0.0.1", port=port, debug=True, threaded=True)
