"""match_evidence: for each requirement, retrieve candidate chunks and assess them.

1. Hybrid retrieval (BM25 + dense + rerank) per requirement.
2. One batched LLM call labels each (requirement, chunk) pair full / partial / none.
3. Strength = verdict gated, reranker-modulated (see scoring.evidence_strength).
"""

from __future__ import annotations

from jobfit.graph.nodes._common import traced
from jobfit.graph.prompts import render
from jobfit.graph.services import Services
from jobfit.graph.state import JobFitState
from jobfit.schemas import AssessmentList, Evidence, JobRequirements
from jobfit.scoring import evidence_strength

BATCH_SIZE = 10  # requirements per assessment call


@traced("match_evidence")
def match_evidence(state: JobFitState, svc: Services) -> dict:
    job = JobRequirements.model_validate(state["requirements"])
    retriever = svc.make_retriever()

    candidates: dict[str, list] = {}
    for r in job.requirements:
        query = r.text if r.category != "language" else f"{r.text} (spoken languages)"
        candidates[r.id] = retriever.search(query, k=svc.settings.evidence_top_k)

    evidence: dict[str, list[dict]] = {r.id: [] for r in job.requirements}
    reqs = [r for r in job.requirements if candidates[r.id]]
    for start in range(0, len(reqs), BATCH_SIZE):
        batch = reqs[start : start + BATCH_SIZE]
        pairs_ctx = [
            {
                "requirement_id": r.id,
                "requirement": r.text,
                "category": r.category,
                "years": r.years,
                "chunks": [
                    {
                        "chunk_id": h.chunk.id,
                        "section": h.chunk.section,
                        "date_range": h.chunk.date_range,
                        "text": h.chunk.text,
                        "retrieval_score": h.score,
                    }
                    for h in candidates[r.id]
                ],
            }
            for r in batch
        ]
        system, user = render("assess_evidence", pairs=_format_pairs(pairs_ctx))
        result = svc.writer.structured(
            "assess_evidence", system, user, AssessmentList, context={"pairs": pairs_ctx}
        )

        by_pair = {(a.requirement_id, a.chunk_id): a for a in result.items}
        for r in batch:
            for hit in candidates[r.id]:
                a = by_pair.get((r.id, hit.chunk.id))
                if a is None or a.support == "none":
                    continue
                # Only accept a quote that really is in the chunk; otherwise cite the whole chunk.
                quote = a.quote.strip() if a.quote and a.quote.strip() in hit.chunk.text else hit.chunk.text
                evidence[r.id].append(
                    Evidence(
                        requirement_id=r.id,
                        chunk_id=hit.chunk.id,
                        quote=quote,
                        strength=evidence_strength(a.support, hit.score),
                        retrieval_score=round(hit.score, 4),
                        assessment=a.support,
                    ).model_dump()
                )
            evidence[r.id].sort(key=lambda e: -e["strength"])

    return {"evidence": evidence}


def _format_pairs(pairs_ctx: list[dict]) -> str:
    lines = []
    for p in pairs_ctx:
        years = f" (asks for {p['years']}+ years)" if p["years"] else ""
        lines.append(f"## Requirement {p['requirement_id']}: {p['requirement']}{years}")
        for c in p["chunks"]:
            dates = f" | dates: {c['date_range']}" if c["date_range"] else ""
            lines.append(f"- chunk_id: {c['chunk_id']} | from: {c['section']}{dates}\n  text: {c['text']}")
        lines.append("")
    return "\n".join(lines)
