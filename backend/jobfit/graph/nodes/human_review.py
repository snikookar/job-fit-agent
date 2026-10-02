"""human_review: pause the graph with `interrupt()` until the user approves or edits the draft.

The graph state is checkpointed, so the pause can last minutes or days, and survives a
server restart. The API resumes it with `Command(resume=ReviewDecision)`.

Sentences the user edited are fact-checked again. Unsupported edits are removed (and
reported) unless the user explicitly chose to keep them: the human has the last word,
but it has to be a conscious decision.

Note: LangGraph re-runs this node from the top on resume, so nothing expensive happens
before `interrupt()`.
"""

from __future__ import annotations

from langgraph.types import interrupt

from jobfit.graph.nodes._common import traced
from jobfit.graph.services import Services
from jobfit.graph.state import JobFitState
from jobfit.grounding import drop_unsupported, iter_sentences, judge_draft
from jobfit.schemas import Draft, ReviewDecision


@traced("human_review")
def human_review(state: JobFitState, svc: Services) -> dict:
    raw = interrupt(
        {
            "draft": state.get("draft"),
            "verdicts": state.get("verdicts", []),
            "removed": state.get("removed", []),
        }
    )
    decision = ReviewDecision.model_validate(raw)
    if not decision.approved:
        return {"approved": False, "review_note": decision.note}

    proposed = Draft.model_validate(state["draft"])
    final = decision.draft or proposed
    original = {(sec, s.text, tuple(s.evidence_ids)) for sec, _, s in iter_sentences(proposed)}
    edited = {
        (sec, i) for sec, i, s in iter_sentences(final) if (sec, s.text, tuple(s.evidence_ids)) not in original
    }
    verdicts = (
        judge_draft(final, state.get("job_text", ""), svc.judge, svc.settings.judge_threshold, only=edited)
        if edited
        else []
    )
    removed = list(state.get("removed") or [])
    if not decision.keep_unsupported_edits:
        bad = [v for v in verdicts if not v.supported]
        if bad:
            final = drop_unsupported(final, verdicts)
            removed += [v.model_dump() | {"edited_by_user": True} for v in bad]
            verdicts = [v for v in verdicts if v.supported]

    return {
        "approved": True,
        "final_draft": final.model_dump(),
        "final_verdicts": [v.model_dump() for v in verdicts],
        "removed": removed,
        "review_note": decision.note,
    }
