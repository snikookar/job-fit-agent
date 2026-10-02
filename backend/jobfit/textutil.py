"""Small text helpers shared by retrieval, the heuristic LLM and the grounding checks."""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-]*[a-z0-9+#]|[a-z0-9]", re.IGNORECASE)

STOPWORDS = frozenset(
    """a an and are as at be been being by can could did do does for from had has have he her his
    i in into is it its me my of on or our over she should so than that the their them then there
    these they this to too up us was we were what when where which while who will with would you
    your yours also very more most such using use used via per across within about after before
    work worked working strong good great solid experience experienced years year plus ability
    able knowledge familiarity familiar understanding skills skill including include etc e.g
    must nice have having required requirements preferred bonus least minimum ideally team""".split()
)

NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(\s*%|\+)?")
NUMBER_WORDS = {
    # "one" is left out on purpose: "one of", "one area" are far more common than "one year".
    "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15",
    "twenty": "20", "thirty": "30", "fifty": "50", "hundred": "100",
    "dozen": "12", "zwei": "2", "drei": "3", "vier": "4", "fünf": "5", "zehn": "10",
}
_NUMBER_WORD_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens. Keeps tech-ish tokens like `c++`, `c#`, `node.js`, `gpt-4`."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def stem(token: str) -> str:
    """A deliberately tiny stemmer: enough to match `apis`/`api` and `deployed`/`deploy`."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def content_terms(text: str) -> set[str]:
    """Stemmed tokens without stopwords: the 'meaning-carrying' words of a sentence."""
    return {stem(t) for t in tokenize(text) if t not in STOPWORDS and len(t) > 1}


def extract_numbers(text: str) -> set[str]:
    """Numbers that appear as claims ('5 years', '23%', 'two engineers').

    Normalizes '1,2' -> '1.2' and number words -> digits, so "two" and "2" match.
    """
    found = {m.group(1).replace(",", ".") for m in NUMBER_RE.finditer(text)}
    found |= {NUMBER_WORDS[m.group(1).lower()] for m in _NUMBER_WORD_RE.finditer(text)}
    return found


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9\"'(])", text.strip())
    return [p.strip() for p in parts if p.strip()]
