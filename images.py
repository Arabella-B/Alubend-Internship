"""Find primary-source images on Wikimedia Commons.

Commons holds digitised collections from national archives, libraries and museums
(the US National Archives, the Library of Congress, the Imperial War Museum, the
Bundesarchiv, many national libraries) with catalogue metadata: who made each item,
when, where it came from and under what licence. Claude searches it through the
`find_images` tool, judges each candidate from that metadata, and the briefing can
only show files that a search actually returned, so every image is real and credited.
"""

from __future__ import annotations

import html
import json
import re
import ssl
import threading
import urllib.parse
import urllib.request

import certifi

API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia asks automated clients to identify themselves with a project link.
USER_AGENT = "ThenAndNow/1.0 (https://github.com/Arabella-B/Alubend-Internship)"
THUMB_WIDTH = 960
MIN_WIDTH = 300  # anything smaller is too low-resolution to read
RESULTS_PER_SEARCH = 8
_SSL = ssl.create_default_context(cafile=certifi.where())
_TAGS = re.compile(r"<[^>]+>")

FIND_IMAGES_TOOL = {
    "name": "find_images",
    "description": "Search Wikimedia Commons for primary-source images: photographs, artifacts, "
    "documents, posters, political cartoons, and maps or charts. Commons holds digitised "
    "collections from archives, libraries and museums worldwide. Returns up to 8 candidates, "
    "each with its file name, catalogue description, date, creator, original source, "
    "categories and licence. Search in English and, where useful, in the languages of the "
    "places involved. Use specific queries (event, place, year, type of item), e.g. "
    "'Tehran August 1953 crowd' or 'Korea 1945 map 38th parallel'. You can request several "
    "searches at once.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["query"],
        "properties": {"query": {"type": "string", "description": "What to search for."}},
    },
}


def _text(value: str, limit: int) -> str:
    """Commons metadata is HTML; reduce it to plain text."""
    value = html.unescape(_TAGS.sub(" ", value or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _meta(info: dict, key: str, limit: int = 300) -> str:
    return _text(info.get("extmetadata", {}).get(key, {}).get("value", ""), limit)


def _get(params: dict) -> dict:
    query = urllib.parse.urlencode({"format": "json", "formatversion": "2", **params})
    request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, context=_SSL, timeout=12) as response:
        return json.load(response)


def search_commons(query: str) -> list:
    """Search Commons and return usable image candidates with their metadata."""
    data = _get(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap|drawing",
            "gsrnamespace": "6",  # File: pages only
            "gsrlimit": str(RESULTS_PER_SEARCH),
            "prop": "imageinfo|categories",
            "clshow": "!hidden",
            "cllimit": "max",
            "iiprop": "url|mime|size|extmetadata",
            "iiurlwidth": str(THUMB_WIDTH),
            "iiextmetadatafilter": "ObjectName|ImageDescription|DateTimeOriginal|Artist|Credit|"
            "LicenseShortName|LicenseUrl",
        }
    )
    pages = sorted(data.get("query", {}).get("pages", []), key=lambda p: p.get("index", 0))
    results = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        if not info.get("mime", "").startswith("image/") or info.get("width", 0) < MIN_WIDTH:
            continue
        results.append(
            {
                "file": page["title"],
                "description": _meta(info, "ImageDescription", 500) or _meta(info, "ObjectName"),
                "date": _meta(info, "DateTimeOriginal", 80),
                "creator": _meta(info, "Artist", 160),
                "original_source": _meta(info, "Credit", 200),
                "categories": [c["title"].removeprefix("Category:") for c in page.get("categories", [])][:8],
                "licence": _meta(info, "LicenseShortName", 60),
                # Kept for display; not shown to Claude.
                "_image_url": info.get("thumburl") or info.get("url", ""),
                "_page_url": info.get("descriptionurl", ""),
                "_licence_url": _meta(info, "LicenseUrl", 200),
                "_width": info.get("thumbwidth") or info.get("width"),
                "_height": info.get("thumbheight") or info.get("height"),
            }
        )
    return results


class ImageResearch:
    """The image searches made during one briefing, and the files they returned."""

    MAX_SEARCHES = 8

    def __init__(self) -> None:
        self.seen: dict = {}
        self.searches = 0
        self._lock = threading.Lock()

    def find_images(self, tool_input: dict) -> tuple:
        """Run one find_images call. Returns (content for Claude, is_error)."""
        query = str(tool_input.get("query", "")).strip()[:200]
        with self._lock:
            self.searches += 1
            over_limit = self.searches > self.MAX_SEARCHES
        if not query:
            return "Provide a search query.", True
        if over_limit:
            return "Image search limit reached. Choose from the images already found.", True
        try:
            results = search_commons(query)
        except Exception as exc:  # network trouble shouldn't sink the briefing
            return f"Image search failed ({exc.__class__.__name__}). Try again or continue without it.", True
        with self._lock:
            for item in results:
                self.seen[item["file"]] = item
        if not results:
            return "No images found. Try different or more specific terms.", False
        public = [{k: v for k, v in item.items() if not k.startswith("_")} for item in results]
        return json.dumps(public, ensure_ascii=False), False

    def attach(self, images: list, limit: int = 6) -> list:
        """Keep only images a search returned, adding their real URLs and credits."""
        kept, used = [], set()
        for image in images or []:
            item = self.seen.get(str(image.get("file", "")).strip())
            if not item or item["file"] in used or not item["_image_url"]:
                continue
            used.add(item["file"])
            kept.append(
                {
                    **image,
                    "image_url": item["_image_url"],
                    "page_url": item["_page_url"],
                    "width": item["_width"],
                    "height": item["_height"],
                    "credit": {
                        "creator": item["creator"],
                        "date": item["date"],
                        "source": item["original_source"],
                        "licence": item["licence"],
                        "licence_url": item["_licence_url"],
                    },
                }
            )
            if len(kept) == limit:
                break
        return kept
