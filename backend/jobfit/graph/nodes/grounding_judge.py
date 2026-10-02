"""grounding_judge: check every sentence against its evidence; drive the revision loop.

- All sentences supported           -> human_review
- Some unsupported, rounds left     -> back to writer with feedback
- Some unsupported, no rounds left  -> remove them, report them, go to human_review
"""

from __future__ import annotations

from jobfit.graph.nodes._common import traced
from jobfit.graph.services import Services
from jobfit.graph.state import JobFitState
from jobfit.grounding import drop_unsupported, judge_draft
from jobfit.schemas import Draft, Verdict


@traced("grounding_judge")
def grounding_judge(state: JobFitState, svc: Services) -> dict:
    draft = Draft.model_validate(state["draft"])
    previous = [Verdict.model_validate(v) for v in state.get("verdicts") or []]
    verdicts = judge_draft(
        draft, state.get("job_text", ""), svc.judge, svc.settings.judge_threshold, cache=previous
    )
    unsupported = [v for v in verdicts if not v.supported]

    if unsupported and state.get("revision", 0) >= svc.settings.max_draft_rounds:
        kept = drop_unsupported(draft, verdicts)
        # Re-index the surviving verdicts so they line up with the trimmed draft.
        survivors: list[Verdict] = []
        for section in ("bullets", "cover_letter"):
            ok = [v for v in verdicts if v.section == section and v.supported]
            survivors += [v.model_copy(update={"index": i}) for i, v in enumerate(ok)]
        return {
            "draft": kept.model_dump(),
            "verdicts": [v.model_dump() for v in survivors],
            "removed": [v.model_dump() for v in unsupported],
        }

    return {"verdicts": [v.model_dump() for v in verdicts], "removed": []}


def route_after_judge(state: JobFitState) -> str:
    if any(not v["supported"] for v in state.get("verdicts") or []):
        return "writer"
    return "human_review"
