"""score: deterministic weighted fit score (no LLM)."""

from __future__ import annotations

from jobfit.graph.nodes._common import traced
from jobfit.graph.services import Services
from jobfit.graph.state import JobFitState
from jobfit.schemas import Evidence, JobRequirements
from jobfit.scoring import compute_score


@traced("score")
def score(state: JobFitState, svc: Services) -> dict:
    job = JobRequirements.model_validate(state["requirements"])
    evidence = {
        rid: [Evidence.model_validate(e) for e in items]
        for rid, items in state.get("evidence", {}).items()
    }
    breakdown = compute_score(job.requirements, evidence, svc.settings.gap_threshold)
    return {"score": breakdown.model_dump()}
