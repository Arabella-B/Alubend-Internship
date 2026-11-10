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

import audiences

CACHE_SECONDS = 600
MAX_PER_FEED = 15
# Newsround lists many videos first, so read further down the feed before filtering.
SCAN_PER_FEED = 60

_ssl_context = ssl.create_default_context(cafile=certifi.where())
# Per feed URL: (time fetched, items). Age groups that share feeds share the cache.
_cache: Dict[str, tuple] = {}

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
        if len(items) >= SCAN_PER_FEED:
            break
    return items


def _feed(source: str, url: str, force: bool) -> List[dict]:
    cached = _cache.get(url)
    if not force and cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]
    items = _fetch_feed(source, url)
    if items:
        _cache[url] = (time.time(), items)
    elif cached:
        items = cached[1]  # keep showing the last good copy if a feed is briefly down
    return items


def get_headlines(audience: str = audiences.DEFAULT, force: bool = False) -> List[dict]:
    """Recent headlines for an age group, newest first (each feed cached for 10 minutes)."""
    feeds = audiences.get(audience)["feeds"]
    with ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        results = pool.map(lambda kv: _feed(kv[0], kv[1], force), feeds.items())
    items = []
    for feed_items in results:
        items += [item for item in feed_items if audiences.suitable(item, audience)][:MAX_PER_FEED]
    items.sort(key=lambda i: i["timestamp"], reverse=True)
    return items
