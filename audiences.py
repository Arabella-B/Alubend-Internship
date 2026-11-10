"""Age groups: which news each one sees, and how briefings are written for it."""

from __future__ import annotations

import re

# Stories on these topics are left out of the younger groups' headline lists.
# Readers can still bring their own story; the writing guidance below keeps it age-appropriate.
_SENSITIVE = re.compile(
    r"\b(rap(e|ed|es|ing|ist)|sexual(ly)?|sex (abuse|offen|attack|traffick|crime)|paedophil|pedophil|"
    r"porn|child abuse|grooming|incest|molest|prostitut|suicide|self-harm|behead|decapitat|"
    r"dismember|mutilat)",
    re.IGNORECASE,
)
_YOUNG_EXTRA = re.compile(
    r"\b(murder(ed|er|s)?|massacre|stabb(ed|ing)|shooting|gunman|killed|corpse|bodies|executed|"
    r"execution|overdose|drugs?|tortur(e|ed|ing))\b",
    re.IGNORECASE,
)
# Items in children's feeds that are videos or programme listings, not stories.
_NOT_A_STORY = re.compile(r"^(watch newsround|newsround\b.*\bbulletin)", re.IGNORECASE)

ADULT_FEEDS = {
    "BBC News": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "NPR": "https://feeds.npr.org/1001/rss.xml",
    "The Guardian": "https://www.theguardian.com/world/rss",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
}

AUDIENCES = {
    "11-13": {
        "label": "Ages 11–13",
        "tagline": "The history behind the news, explained clearly",
        "blurb": "News written for young readers, with history told in clear, simple language.",
        "feeds": {
            "BBC Newsround": "https://feeds.bbci.co.uk/newsround/rss.xml",
            "Kiwi Kids News": "https://www.kiwikidsnews.co.nz/feed/",
            "Science News Explores": "https://www.snexplores.org/feed",
        },
        "filters": [_SENSITIVE, _YOUNG_EXTRA],
        "guidance": """Your reader is 11 to 13 years old. Write for them:
- Use short sentences and everyday words. Explain every name, place and idea the first \
time it appears, and give a sense of when things happened ("about 70 years ago").
- Stay accurate and don't talk down. Keep the same standards as for any reader: go back to \
the deep roots, tell the story from more than one side, and explain why people disagree, \
in simple terms.
- Describe wars, violence and suffering honestly but without graphic detail. Leave out \
sexual violence and other adult themes; if a story can't be understood without them, \
mention them only in general, non-graphic words.
- Keep it shorter than usual: 3-5 short paragraphs of background, 6-10 timeline entries, \
1-2 parallels, and 3-5 perspectives. This overrides the lengths in the tool descriptions.
- Choose images suitable for this age: no pictures of dead or badly injured people, \
executions or graphic violence, and no frightening propaganda unless you explain it \
carefully. Maps, documents, everyday-life photographs and cartoons often work best.""",
    },
    "13-17": {
        "label": "Ages 13–17",
        "tagline": "The history behind today's headlines, for students",
        "blurb": "World news with the history explained at secondary-school level.",
        "feeds": ADULT_FEEDS,
        "filters": [_SENSITIVE],
        "guidance": """Your reader is 13 to 17 years old, at secondary school. Write for them:
- Use clear language, and explain specialist terms and names the first time they appear. \
You can include more complexity than for younger readers, such as how historians' \
interpretations differ and why.
- Show the skills they use in school history: how evidence is used, how sources can be \
biased, and how interpretations change over time.
- Describe violence factually, without gratuitous or graphic detail. Mention sexual \
violence, suicide and similar topics only where they are essential to the history, \
briefly and without detail.
- Choose images suitable for this age: avoid graphic pictures of dead or badly injured \
people.""",
    },
    "18-plus": {
        "label": "Ages 18+",
        "tagline": "The history behind today's headlines",
        "blurb": "The full briefing, written for adult readers.",
        "feeds": ADULT_FEEDS,
        "filters": [],
        "guidance": "",
    },
}

DEFAULT = "18-plus"


def get(key: str) -> dict:
    return AUDIENCES.get(key or DEFAULT, AUDIENCES[DEFAULT])


def resolve(key: str) -> str:
    return key if key in AUDIENCES else DEFAULT


def suitable(item: dict, key: str) -> bool:
    """Whether a headline belongs in this age group's list."""
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    if _NOT_A_STORY.search(item.get("title", "")):
        return False
    return not any(pattern.search(text) for pattern in get(key)["filters"])
