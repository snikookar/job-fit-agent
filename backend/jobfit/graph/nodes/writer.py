"""writer: tailored resume bullets + cover letter, every sentence citing evidence ids.

On a revision round it gets the judge's feedback and must fix or delete the flagged
sentences, keeping the supported ones unchanged.
"""

from __future__ import annotations

from jobfit.graph.nodes._common import traced
from jobfit.graph.prompts import render
from jobfit.graph.services import Services
from jobfit.graph.state import JobFitState
from jobfit.retrieval import store
from jobfit.schemas import Draft, JobRequirements

MAX_POOL = 25
LANGUAGE_NAMES = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "nl": "Dutch", "it": "Italian", "sv": "Swedish"}


def build_evidence_pool(state: JobFitState) -> list[dict]:
    """Unique evidence chunks, strongest first, with the requirements each one supports."""
    job = JobRequirements.model_validate(state["requirements"])
    req_text = {r.id: r.text for r in job.requirements}
    pool: dict[str, dict] = {}
    for rid, items in (state.get("evidence") or {}).items():
        for e in items:
            entry = pool.setdefault(
                e["chunk_id"], {"chunk_id": e["chunk_id"], "quote": e["quote"], "strength": 0.0, "supports": []}
            )
            entry["strength"] = max(entry["strength"], e["strength"])
            entry["supports"].append(req_text.get(rid, rid))
    chunks = store.get_chunks(list(pool))
    for cid, entry in pool.items():
        c = chunks.get(cid)
        entry.update(
            text=c.text if c else entry["quote"],
            section=c.section if c else "",
            date_range=c.date_range if c else None,
            source=c.source if c else "",
        )
    return sorted(pool.values(), key=lambda e: -e["strength"])[:MAX_POOL]


def _format_pool(pool: list[dict]) -> str:
    lines = []
    for e in pool:
        dates = f" | dates: {e['date_range']}" if e["date_range"] else ""
        lines.append(
            f"- chunk_id: {e['chunk_id']} | from: {e['section']}{dates}\n"
            f"  supports: {'; '.join(e['supports'])}\n  text: {e['text']}"
        )
    return "\n".join(lines) or "(no evidence found)"


def _revision_block(state: JobFitState) -> str:
    verdicts = state.get("verdicts") or []
    if not verdicts or not state.get("draft"):
        return ""
    lines = [
        "",
        "# Your previous draft was fact-checked",
        "Keep every SUPPORTED sentence exactly as it is (text and evidence_ids). For each "
        "UNSUPPORTED sentence, either rewrite it so that it only says what the cited evidence "
        "says, or delete it.",
        "",
    ]
    for v in verdicts:
        status = "SUPPORTED" if v["supported"] else f"UNSUPPORTED: {v['reason']}"
        lines.append(f"- [{v['section']} #{v['index']}] {v['text']} (cites {', '.join(v['evidence_ids'])}) -> {status}")
    return "\n".join(lines)


@traced("writer")
def writer(state: JobFitState, svc: Services) -> dict:
    job = JobRequirements.model_validate(state["requirements"])
    pool = build_evidence_pool(state)
    gaps = state.get("gaps") or []
    revision = state.get("revision", 0)
    language = LANGUAGE_NAMES.get(state.get("language", "en"), "English")

    system, user = render(
        "writer",
        min_bullets=4,
        max_bullets=7,
        min_letter=5,
        max_letter=9,
        language=language,
        title=job.title,
        company=job.company or "(not stated)",
        requirements="\n".join(f"- ({r.importance}) {r.text}" for r in job.requirements),
        evidence=_format_pool(pool),
        gaps="\n".join(f"- ({g['importance']}) {g['text']}" for g in gaps) or "(none)",
        revision_block=_revision_block(state) if revision else "",
    )
    draft = svc.writer.structured(
        "write_draft",
        system,
        user,
        Draft,
        context={
            "job": job.model_dump(),
            "pool": pool,
            "gaps": gaps,
            "revision": revision,
            "previous_draft": state.get("draft"),
            "verdicts": state.get("verdicts"),
        },
    )
    return {"draft": draft.model_dump(), "revision": revision + 1}
