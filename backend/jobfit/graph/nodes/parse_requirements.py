"""parse_requirements: job text -> JobRequirements (LLM structured output)."""

from __future__ import annotations

from jobfit.graph.nodes._common import traced
from jobfit.graph.prompts import render
from jobfit.graph.services import Services
from jobfit.graph.state import JobFitState
from jobfit.schemas import JobRequirements

MAX_REQUIREMENTS = 30


@traced("parse_requirements")
def parse_requirements(state: JobFitState, svc: Services) -> dict:
    hints = state.get("job_hints") or {}
    system, user = render(
        "parse_requirements", language=state.get("language", "unknown"), job_text=state["job_text"]
    )
    parsed = svc.writer.structured(
        "parse_requirements",
        system,
        user,
        JobRequirements,
        context={
            "job_text": state["job_text"],
            "title_hint": hints.get("title"),
            "company_hint": hints.get("company"),
            "location_hint": hints.get("location"),
        },
    )
    return {"requirements": normalize(parsed, hints).model_dump()}


def normalize(parsed: JobRequirements, hints: dict) -> JobRequirements:
    """Deduplicate, cap and renumber requirements; fill blanks from structured ATS data."""
    seen: set[str] = set()
    reqs = []
    for r in parsed.requirements:
        key = " ".join(r.text.lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        reqs.append(r)
    reqs = reqs[:MAX_REQUIREMENTS]
    for i, r in enumerate(reqs, start=1):
        r.id = f"r{i}"
    if not reqs:
        raise ValueError(
            "No requirements could be extracted from this posting. "
            "Check that the text contains the requirements section."
        )
    return parsed.model_copy(
        update={
            "requirements": reqs,
            "title": parsed.title or hints.get("title") or "Untitled position",
            "company": parsed.company or hints.get("company"),
            "location": parsed.location or hints.get("location"),
        }
    )
