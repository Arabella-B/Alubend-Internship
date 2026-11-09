"""Fetch current headlines from public RSS feeds."""

from __future__ import annotations

import html
import re
import ssl
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

import certifi

FEEDS: Dict[str, str] = {
    "BBC News": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "NPR": "https://feeds.npr.org/1001/rss.xml",
    "The Guardian": "https://www.theguardian.com/world/rss",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
}

CACHE_SECONDS = 600
MAX_PER_FEED = 15

_ssl_context = ssl.create_default_context(cafile=certifi.where())
_cache: Dict[str, object] = {"time": 0.0, "items": []}

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _timestamp(pub_date: str) -> float:
    try:
        return parsedate_to_datetime(pub_date).timestamp()
    except (TypeError, ValueError, IndexError):
        return 0.0


def _fetch_feed(source: str, url: str) -> List[dict]:
    request = urllib.request.Request(url, headers={"User-Agent": "HistoricalContextApp/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=10, context=_ssl_context) as response:
            root = ET.fromstring(response.read())
    except Exception as exc:  # one broken feed shouldn't break the page
        print(f"[feeds] {source} failed: {exc}")
        return []

    items = []
    for item in root.iter("item"):
        title = _clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if not title or not link.startswith("http"):
            continue
        pub_date = item.findtext("pubDate") or ""
        items.append(
            {
                "source": source,
                "title": title,
                "summary": _clean(item.findtext("description"))[:400],
                "url": link,
                "published": pub_date,
                "timestamp": _timestamp(pub_date),
            }
        )
        if len(items) >= MAX_PER_FEED:
            break
    return items


def get_headlines(force: bool = False) -> List[dict]:
    """Return recent headlines from all feeds, newest first (cached for 10 minutes)."""
    if not force and _cache["items"] and time.time() - float(_cache["time"]) < CACHE_SECONDS:
        return list(_cache["items"])  # type: ignore[arg-type]

    with ThreadPoolExecutor(max_workers=len(FEEDS)) as pool:
        results = pool.map(lambda kv: _fetch_feed(*kv), FEEDS.items())
    items = [item for feed_items in results for item in feed_items]
    items.sort(key=lambda i: i["timestamp"], reverse=True)

    if items:
        _cache["time"] = time.time()
        _cache["items"] = items
    return items
