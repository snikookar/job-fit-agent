"""Deterministic fit scoring. No LLM involved: the same evidence always gives the same score.

    score = 100 * sum(weight_i * strength_i) / sum(weight_i)

weight is 2 for "must" requirements and 1 for "nice" ones; strength is the best evidence
strength (0..1) found for the requirement. Every point of the score can be traced back to
a requirement and a piece of evidence, which is what makes it explainable.
"""

from __future__ import annotations

from jobfit.schemas import Evidence, Requirement, RequirementScore, ScoreBreakdown

WEIGHTS = {"must": 2.0, "nice": 1.0}
SUPPORT_VALUE = {"full": 1.0, "partial": 0.5, "none": 0.0}


def evidence_strength(support: str, retrieval_score: float) -> float:
    """Combine the LLM's support verdict with the reranker score.

    The verdict gates the strength (no support -> 0, however similar the text looks);
    the reranker score modulates it within the verdict's range:
    full: 0.6..1.0, partial: 0.3..0.5, none: 0.
    """
    value = SUPPORT_VALUE[support]
    retrieval_score = min(max(retrieval_score, 0.0), 1.0)
    return round(value * (0.6 + 0.4 * retrieval_score), 4)


def best_strength(evidence: list[Evidence]) -> float:
    return max((e.strength for e in evidence), default=0.0)


def compute_score(
    requirements: list[Requirement],
    evidence: dict[str, list[Evidence]],
    gap_threshold: float = 0.5,
) -> ScoreBreakdown:
    items: list[RequirementScore] = []
    for r in requirements:
        weight = WEIGHTS[r.importance]
        strength = best_strength(evidence.get(r.id, []))
        items.append(
            RequirementScore(
                requirement_id=r.id,
                text=r.text,
                importance=r.importance,
                weight=weight,
                strength=round(strength, 4),
                contribution=round(weight * strength, 4),
            )
        )
    total_weight = sum(i.weight for i in items)
    score = 100.0 * sum(i.contribution for i in items) / total_weight if total_weight else 0.0
    musts = [i for i in items if i.importance == "must"]
    must_coverage = (
        sum(1 for i in musts if i.strength >= gap_threshold) / len(musts) if musts else 1.0
    )
    return ScoreBreakdown(score=round(score, 1), must_coverage=round(must_coverage, 3), items=items)
