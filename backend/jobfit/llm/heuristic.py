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
from datetime import date
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
        m = re.search(r"\b(?:at|join|About)[ \t]+([A-Z][\w&.\-]+(?:[ \t]+[A-Z][\w&.\-]+){0,3})", text)
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


# --- assess_evidence ----------------------------------------------------------------

NEGATION_RE = re.compile(r"\b(not|never|no|without|haven't|hasn't|didn't|nicht|kein\w*)\b", re.IGNORECASE)
LEARNING_RE = re.compile(r"\b(learning|course|tutorial|experimented|notes)\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def span_years(date_range: str | None, current_year: int | None = None) -> float | None:
    """Rough length of a date range in years ("03/2022 – present" -> ~4)."""
    if not date_range:
        return None
    years = [int(y) for y in _YEAR_RE.findall(date_range)]
    if re.search(r"present|current|now|today|heute|aktuell", date_range, re.IGNORECASE):
        years.append(current_year or date.today().year)
    if len(years) < 2:
        return None
    return max(years) - min(years)


def _best_sentence(text: str, terms: set[str], tags: set[str]) -> str:
    from jobfit.textutil import content_terms, split_sentences

    for sentence in split_sentences(text):
        if terms & content_terms(sentence) or tags & set(extract_tech_tags(sentence)):
            return sentence
    return text


@handler("assess_evidence")
def assess_evidence(ctx: dict[str, Any]) -> dict[str, Any]:
    from jobfit.textutil import content_terms

    items = []
    for p in ctx["pairs"]:
        req = p["requirement"]
        req_terms = content_terms(req)
        req_tags = set(extract_tech_tags(req))
        is_language = p.get("category") == "language"
        langs = {lang for lang in _LANGUAGES if lang in req.lower()}
        for c in p["chunks"]:
            text = c["text"]
            chunk_terms = content_terms(f"{c['section']} {text}")
            chunk_tags = set(extract_tech_tags(f"{c['section']} {text}"))
            term_ratio = len(req_terms & chunk_terms) / len(req_terms) if req_terms else 0.0

            if is_language and langs:
                support = "full" if all(lang in text.lower() for lang in langs) else "none"
            elif NEGATION_RE.search(text) and (req_tags & chunk_tags or term_ratio >= 0.5):
                support = "none"  # "I have not run Kubernetes in production"
            elif req_tags:
                tag_ratio = len(req_tags & chunk_tags) / len(req_tags)
                support = "full" if tag_ratio == 1 else "partial" if tag_ratio > 0 else (
                    "partial" if term_ratio >= 0.5 else "none"
                )
            else:
                support = "full" if term_ratio >= 0.6 else "partial" if term_ratio >= 0.3 else "none"

            if support == "full":
                span = span_years(c.get("date_range"))
                stated = max((int(y) for y in YEARS_RE.findall(text)), default=None)  # "6+ years"
                known = max(x for x in (span, stated, -1) if x is not None)
                if p.get("years") and known < p["years"]:
                    support = "partial"  # can't confirm the years from this chunk alone
                elif LEARNING_RE.search(text):
                    support = "partial"

            quote = _best_sentence(text, req_terms, req_tags) if support != "none" else ""
            items.append(
                {"requirement_id": p["requirement_id"], "chunk_id": c["chunk_id"], "support": support, "quote": quote}
            )
    return {"items": items}


# --- gap_suggestions ----------------------------------------------------------------


@handler("gap_suggestions")
def gap_suggestions(ctx: dict[str, Any]) -> dict[str, Any]:
    items = []
    for g in ctx["gaps"]:
        if g["importance"] == "must":
            text = (
                f"Must-have with little evidence: \"{g['requirement']}\". If you have this experience, "
                "add it to your resume or a project write-up so it can be cited. Otherwise, build it "
                "with a small project and address it openly in your cover letter."
            )
        else:
            text = (
                "Nice to have. If you've used this, add a line about it to your profile; "
                "otherwise you can leave it out."
            )
        items.append({"requirement_id": g["requirement_id"], "suggestion": text})
    return {"items": items}


# --- write_draft ----------------------------------------------------------------------

_PAST_VERBS = {"built", "led", "ran", "wrote", "made", "set", "took", "drove", "grew", "won", "taught"}


def _clean_quote(text: str) -> str:
    text = " ".join(line.strip().lstrip("-*• ").strip() for line in text.splitlines() if line.strip())
    return text if text.endswith((".", "!", "?")) else text + "."


def _first_person(quote: str) -> str:
    first = quote.split()[0].lower() if quote.split() else ""
    if first.endswith("ed") or first in _PAST_VERBS:
        return f"In my work, I {quote[0].lower()}{quote[1:]}"
    return f"My profile includes this: {quote}"


@handler("write_draft")
def write_draft(ctx: dict[str, Any]) -> dict[str, Any]:
    from jobfit.schemas import JOB_EVIDENCE_ID

    if ctx.get("revision") and ctx.get("previous_draft"):
        # Revision: the heuristic can't rewrite, so it deletes what the judge flagged.
        bad = {(v["section"], v["index"]) for v in ctx.get("verdicts") or [] if not v["supported"]}
        prev = ctx["previous_draft"]
        return {
            section: [s for i, s in enumerate(prev[section]) if (section, i) not in bad]
            for section in ("bullets", "cover_letter")
        }

    pool = ctx["pool"]
    job = ctx["job"]
    company = job.get("company") or "your company"

    # Bullets: the strongest evidence, resume bullets first, reused nearly verbatim.
    # Achievement bullets from the experience section beat skill lists and README text.
    ranked = sorted(
        pool,
        key=lambda e: (
            not e.get("section", "").startswith("Experience"),
            not e.get("source", "").startswith("resume"),
            -e["strength"],
        ),
    )
    bullets = [
        {"text": _clean_quote(e["quote"]), "evidence_ids": [e["chunk_id"]]}
        for e in ranked[:6]
    ]

    letter = [
        {"text": f"I am applying for the {job['title']} position at {company}.", "evidence_ids": [JOB_EVIDENCE_ID]}
    ]
    for e in ranked[:3]:
        letter.append({"text": _first_person(_clean_quote(e["quote"])), "evidence_ids": [e["chunk_id"]]})
    must_gaps = [g for g in ctx.get("gaps") or [] if g["importance"] == "must"]
    if must_gaps:
        letter.append(
            {
                "text": f"One requirement I have not yet fully met is \"{must_gaps[0]['text']}\", and I am keen to build it.",
                "evidence_ids": [JOB_EVIDENCE_ID],
            }
        )
    letter.append(
        {"text": f"I would welcome the chance to discuss how I can contribute to {company}.", "evidence_ids": [JOB_EVIDENCE_ID]}
    )
    return {"bullets": bullets, "cover_letter": letter}


# --- judge ------------------------------------------------------------------------------

# Words that carry no factual claim in application prose.
_PROSE_WORDS = {
    "applying", "position", "role", "company", "chance", "discuss", "contribute", "welcome",
    "keen", "excited", "believe", "profile", "includes", "work", "my", "built", "help", "helped",
    "would", "like", "glad", "happy", "opportunity", "bring", "apply", "relevant", "fit",
}
CLAIM_RE = re.compile(
    r"\b(built|led|developed|designed|implemented|deployed|managed|created|shipped|delivered|"
    r"architected|owned|ran|mentored|years of|expert|proficient)\b",
    re.IGNORECASE,
)


@handler("judge")
def judge(ctx: dict[str, Any]) -> dict[str, Any]:
    from jobfit.schemas import JOB_EVIDENCE_ID
    from jobfit.textutil import content_terms

    items = []
    for s in ctx["sentences"]:
        text = s["text"]
        profile_ev = " ".join(e["text"] for e in s["evidence"] if e["id"] != JOB_EVIDENCE_ID)
        job_ev = " ".join(e["text"] for e in s["evidence"] if e["id"] == JOB_EVIDENCE_ID)
        tags = set(extract_tech_tags(text))

        if not profile_ev:
            # Only the job posting is cited: fine for statements about the role, not for claims.
            claim = CLAIM_RE.search(text) and not NEGATION_RE.search(text)
            unknown_tags = tags - set(extract_tech_tags(job_ev))
            if claim:
                items.append(_verdict(s, False, 0.85, "claims experience but cites only the job posting"))
            elif unknown_tags:
                items.append(_verdict(s, False, 0.8, f"mentions {', '.join(sorted(unknown_tags))}, which is not in the job posting"))
            else:
                items.append(_verdict(s, True, 0.8, "statement about the role, no candidate claim"))
            continue

        missing_tags = tags - set(extract_tech_tags(profile_ev))
        if missing_tags:
            items.append(_verdict(s, False, 0.9, f"{', '.join(sorted(missing_tags))} not in the cited evidence"))
            continue
        terms = content_terms(text) - _PROSE_WORDS
        ev_terms = content_terms(profile_ev + " " + job_ev)
        coverage = len(terms & ev_terms) / len(terms) if terms else 1.0
        if coverage >= 0.6:
            items.append(_verdict(s, True, 0.5 + coverage / 2, "content matches the cited evidence"))
        else:
            missing = sorted(terms - ev_terms)[:5]
            items.append(_verdict(s, False, 0.5 + (1 - coverage) / 2, f"not in the evidence: {', '.join(missing)}"))
    return {"items": items}


def _verdict(s: dict[str, Any], supported: bool, confidence: float, reason: str) -> dict[str, Any]:
    return {
        "section": s["section"],
        "index": s["index"],
        "supported": supported,
        "confidence": round(min(confidence, 1.0), 3),
        "reason": reason,
    }
