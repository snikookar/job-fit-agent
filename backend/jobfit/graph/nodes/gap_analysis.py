"""gap_analysis: requirements without enough evidence, with suggestions to close them."""

from __future__ import annotations

from jobfit.graph.nodes._common import traced
from jobfit.graph.prompts import render
from jobfit.graph.services import Services
from jobfit.graph.state import JobFitState
from jobfit.schemas import Gap, GapSuggestionList, JobRequirements, ScoreBreakdown


@traced("gap_analysis")
def gap_analysis(state: JobFitState, svc: Services) -> dict:
    job = JobRequirements.model_validate(state["requirements"])
    breakdown = ScoreBreakdown.model_validate(state["score"])
    strength = {i.requirement_id: i.strength for i in breakdown.items}
    weak = [r for r in job.requirements if strength.get(r.id, 0.0) < svc.settings.gap_threshold]
    if not weak:
        return {"gaps": []}

    evidence = state.get("evidence", {})
    gaps_ctx = [
        {
            "requirement_id": r.id,
            "requirement": r.text,
            "importance": r.importance,
            "category": r.category,
            "best_strength": strength.get(r.id, 0.0),
            "best_evidence": (evidence.get(r.id) or [{}])[0].get("quote"),
        }
        for r in weak
    ]
    gaps_text = "\n".join(
        f"- {g['requirement_id']} ({g['importance']}): {g['requirement']}"
        f" | best evidence: {g['best_evidence'] or 'none found'}"
        for g in gaps_ctx
    )
    system, user = render("gap_analysis", title=job.title, gaps=gaps_text)
    result = svc.writer.structured(
        "gap_suggestions", system, user, GapSuggestionList, context={"gaps": gaps_ctx}
    )
    suggestions = {s.requirement_id: s.suggestion for s in result.items}

    gaps = [
        Gap(
            requirement_id=r.id,
            text=r.text,
            importance=r.importance,
            best_strength=strength.get(r.id, 0.0),
            suggestion=suggestions.get(r.id, "Add evidence for this to your profile if you have it."),
        )
        for r in weak
    ]
    gaps.sort(key=lambda g: (g.importance != "must", g.best_strength))
    return {"gaps": [g.model_dump() for g in gaps]}
