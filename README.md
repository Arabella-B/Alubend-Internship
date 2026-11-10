# Then & Again

A small web app that gives historical context for contemporary news stories.

Pick a headline from today's news (BBC, NPR, The Guardian, Al Jazeera), or paste a headline, link or article of
your own. Claude reads the article, checks recent developments with web search, and writes a briefing with:

- what's happening now and why the history matters
- a narrative background, from deep roots to the present
- a timeline of key moments
- historical parallels: how they're similar, how they differ
- the main perspectives of the people involved
- key terms, questions to watch, and sources
- primary-source images placed beside the part of the story they illustrate

**Reading guides** help you understand historical sources the way a historian would. Click "Reading guide" next to
any source in a briefing, or paste a link or document into "Read a historical source". The guide explains who
produced the source, when and why, what it says in plain words, its key passages and difficult terms, whose
perspective it represents and whose is missing, how far to trust it, and how other groups saw the same events.

**Images** are primary sources only: photographs of the events at the time, artifacts and documents from the
period, political cartoons and posters, and maps or charts with real geographical or statistical information.
Claude searches [Wikimedia Commons](https://commons.wikimedia.org/), which holds digitised collections from
archives, libraries and museums, and judges each candidate from its catalogue record. Decorative, modern,
recreated or poorly documented images are left out, and a briefing can have no images at all. Each image comes with
what it shows, why it matters, a note on who made it and from what viewpoint, and its credit and licence. The app
only shows files a search really returned, so image links can't be invented.

**Age groups.** The home page lets readers choose 11–13, 13–17 or 18+. Each version works the same way, with
news and writing suited to that age:

| Age group | Headlines | Writing |
| --- | --- | --- |
| 11–13 | BBC Newsround, Kiwi Kids News, Science News Explores, with stories about violent crime, sexual abuse and similar topics left out | Short sentences and everyday words, every name and idea explained, no graphic detail, shorter briefings, and no graphic images |
| 13–17 | BBC, NPR, The Guardian, Al Jazeera, with stories about sexual abuse, suicide and similar topics left out | Clear language at secondary-school level, with how historians use evidence and disagree, and no graphic detail or images |
| 18+ | BBC, NPR, The Guardian, Al Jazeera | The full briefing |

Every age group keeps the same standards: deep roots, more than one side, and real sources. The age-group settings
are in `audiences.py`.

## Setup

You need Python 3.9+ and an [Anthropic API key](https://platform.claude.com/).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/python app.py
```

Then open <http://localhost:5050>.

## Deploying to Render

This is a Python server, so it must be a **Web Service** on Render, not a Static Site. A Static Site only shows
"Not Found", because there is no `index.html` in the repo.

Easiest: in Render choose **New → Blueprint**, pick this repo, and enter your `ANTHROPIC_API_KEY` when asked.
`render.yaml` sets up everything else.

Or set it up by hand with **New → Web Service**:

| Setting | Value |
| --- | --- |
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn app:app --worker-class gthread --workers 1 --threads 8 --timeout 300 --bind 0.0.0.0:$PORT` |
| Environment variable | `ANTHROPIC_API_KEY` = your key |

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | (required) | Your Anthropic API key |
| `CONTEXT_MODEL` | `claude-opus-5-5` | Claude model used for briefings |
| `CONTEXT_EFFORT` | `medium` | `low`, `medium`, `high`, `xhigh` or `max`: higher is more thorough but slower and costs more |
| `FAST_MODE` | `1` | `1` uses Claude's fast mode: the same model and quality with up to ~2.5x faster output, at twice the per-token price. `0` turns it off. If your account can't use fast mode, the app falls back to standard speed automatically |
| `PORT` | `5050` | Port for the local server |

## How it works

| File | Role |
| --- | --- |
| `audiences.py` | The age groups: their news feeds, headline filters and writing guidance |
| `feeds.py` | Fetches and caches headlines from public RSS feeds |
| `historian.py` | Calls Claude with web fetch and web search; briefings and reading guides come back through strict tool schemas |
| `images.py` | The `find_images` tool: searches Wikimedia Commons and checks the images Claude picks |
| `app.py` | Flask server: serves the age-group menu (`/`), the pages `/11-13`, `/13-17` and `/18-plus`, `/api/headlines`, `/api/context` and `/api/source` (streamed as server-sent events) |
| `templates/`, `static/` | The web interface |

Each briefing typically costs roughly $0.20–0.80 in API usage with fast mode on (about half that with `FAST_MODE=0`), including web searches. Briefings are cached in memory while the server
runs, so opening the same story again is free.

Briefings are generated by AI and can contain mistakes, so check important details against the listed sources.
