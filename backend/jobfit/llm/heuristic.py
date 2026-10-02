"""Offline, rule-based stand-in for the LLM.

It lets anyone clone the repo and click through the whole flow without API keys, and it
makes tests deterministic. It is NOT meant to be good: requirement extraction relies on
section headings and bullets, and the "writer" mostly reuses the evidence wording. Real
results need `LLM_PROVIDER=api`.

Each task name maps to a handler that reads the structured `context` (never the prompt).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from jobfit.llm.base import T, UsageTracker
from jobfit.profile.tech_tags import extract_tech_tags

Handler = Callable[[dict[str, Any]], dict[str, Any]]
HANDLERS: dict[str, Handler] = {}


def handler(task: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        HANDLERS[task] = fn
        return fn

    return deco


class HeuristicLLM(UsageTracker):
    def __init__(self, role: str = "writer") -> None:
        super().__init__()
        self.name = f"{role}:heuristic"

    def structured(
        self,
        task: str,
        system: str,
        user: str,
        schema: type[T],
        context: dict[str, Any] | None = None,
    ) -> T:
        if task not in HANDLERS:
            raise NotImplementedError(f"heuristic provider has no handler for task {task!r}")
        result = HANDLERS[task](context or {})
        self.record(0, 0, 0.0)
        return schema.model_validate(result)


# --- parse_requirements -------------------------------------------------------------

_MUST_HEADINGS = (
    "requirement", "qualification", "what you bring", "you bring", "you have", "must have",
    "must-have", "your profile", "who you are", "looking for", "what we expect", "about you",
    "your skills", "you'll need", "you will need", "skills", "dein profil", "ihr profil",
    "anforderungen", "das bringst du mit", "was du mitbringst", "qualifikation",
)
_NICE_HEADINGS = (
    "nice to have", "nice-to-have", "preferred", "bonus", "plus", "ideally", "good to have",
    "would be great", "wünschenswert", "von vorteil", "optional",
)
_OTHER_HEADINGS = (
    "responsibilit", "what you'll do", "what you will do", "your role", "the role", "about us",
    "about the", "benefits", "we offer", "what we offer", "perks", "why join", "aufgaben",
    "was wir bieten", "deine aufgaben", "ihre aufgaben", "how to apply", "process", "tasks",
)
_LANGUAGES = ("english", "german", "french", "spanish", "dutch", "italian", "swedish", "deutsch", "englisch")
YEARS_RE = re.compile(r"(\d+)\s*\+?\s*(?:(?:-|–|to)\s*\d+\s*)?(?:years?|yrs|jahre)", re.IGNORECASE)


def _heading_kind(line: str) -> str | None:
    s = line.strip().strip("#*:_ ").lower()
    if not s or len(s) > 60:
        return None
    is_heading = line.strip().startswith("#") or line.strip().endswith(":") or len(s.split()) <= 6
    if not is_heading or line.strip().startswith(("-", "*", "•")):
        return None
    if any(k in s for k in _NICE_HEADINGS):
        return "nice"
    if any(k in s for k in _MUST_HEADINGS):
        return "must"
    if any(k in s for k in _OTHER_HEADINGS):
        return "other"
    return None


def _category(text: str) -> str:
    t = text.lower()
    if any(lang in t for lang in _LANGUAGES) and re.search(
        r"fluen|proficien|speak|written|spoken|native|\b[abc][12]\b|level|skills|kenntnisse", t
    ):
        return "language"
    if re.search(r"degree|bachelor|master|ph\.?d|university|diploma|studium|abschluss", t):
        return "education"
    if re.search(r"based in|relocat|on-?site in|located in|work permit|eu citizen", t):
        return "location"
    if extract_tech_tags(text):
        return "skill"
    if YEARS_RE.search(text) or "experience" in t:
        return "experience"
    return "other"


def _bullet_text(line: str) -> str | None:
    m = re.match(r"^\s*(?:[-*•●▪◦]|\d+[.)])\s+(.*)$", line)
    return m.group(1).strip() if m else None


@handler("parse_requirements")
def parse_requirements(ctx: dict[str, Any]) -> dict[str, Any]:
    text: str = ctx["job_text"]
    lines = [ln.rstrip() for ln in text.splitlines()]

    reqs: list[tuple[str, str]] = []  # (text, importance)
    section: str | None = None
    for line in lines:
        kind = _heading_kind(line)
        if kind:
            section = kind
            continue
        bullet = _bullet_text(line)
        if not bullet or len(bullet) < 6:
            continue
        lowered = bullet.lower()
        if section in ("must", "nice"):
            nice = section == "nice" or any(k in lowered for k in ("a plus", "nice to have", "bonus", "preferred", "ideally"))
            reqs.append((bullet, "nice" if nice else "must"))

    if not reqs:  # no recognizable sections: fall back to tech-ish bullets anywhere
        for line in lines:
            bullet = _bullet_text(line)
            if bullet and (extract_tech_tags(bullet) or YEARS_RE.search(bullet)):
                reqs.append((bullet, "must"))

    requirements = []
    for i, (req_text, importance) in enumerate(reqs[:30], start=1):
        years = YEARS_RE.search(req_text)
        requirements.append(
            {
                "id": f"r{i}",
                "text": req_text.rstrip("."),
                "category": _category(req_text),
                "importance": importance,
                "years": int(years.group(1)) if years else None,
            }
        )

    lowered = text.lower()
    if re.search(r"\bhybrid\b", lowered):
        remote = "hybrid"
    elif re.search(r"\b(fully remote|remote-first|100% remote|remote)\b", lowered):
        remote = "remote"
    elif re.search(r"\b(on-?site|in the office|in-office)\b", lowered):
        remote = "onsite"
    else:
        remote = "unknown"

    if re.search(r"(no|not|unable to|cannot|can't)\s+(offer\s+|provide\s+)?visa sponsorship", lowered):
        visa = "no"
    elif re.search(r"visa sponsorship|relocation (support|package)|we sponsor", lowered):
        visa = "yes"
    else:
        visa = "unknown"

    first_line = next((ln.strip("# ").strip() for ln in lines if ln.strip()), "Untitled position")
    company = ctx.get("company_hint")
    if not company:
        m = re.search(r"\b(?:at|join|About)\s+([A-Z][\w&.\-]+(?:\s+[A-Z][\w&.\-]+){0,3})", text)
        company = m.group(1) if m else None
    location = ctx.get("location_hint")
    if not location:
        m = re.search(r"(?im)^\s*(?:location|standort|ort)\s*:\s*(.+)$", text)
        location = m.group(1).strip() if m else None

    return {
        "title": ctx.get("title_hint") or first_line[:120],
        "company": company,
        "location": location,
        "remote": remote,
        "visa_sponsorship": visa,
        "requirements": requirements,
    }
