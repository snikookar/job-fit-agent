"""The LangGraph state shared by all nodes.

Values are stored as plain dicts/lists (Pydantic `model_dump()` output), not model
instances. Checkpoints are serialized to the database, and plain JSON-like data is the
most portable thing to store and the easiest to send to the frontend. Nodes validate
with the Pydantic models when they read.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class JobFitState(TypedDict, total=False):
    # --- input
    run_id: str  # same as the LangGraph thread id
    job_url: str | None
    job_text_input: str | None

    # --- fetch_job
    job_text: str
    job_source: str
    language: str
    job_hints: dict[str, Any]  # title/company/location from structured ATS data

    # --- parse_requirements
    requirements: dict[str, Any]  # JobRequirements

    # --- match_evidence / score / gap_analysis
    evidence: dict[str, list[dict[str, Any]]]  # requirement_id -> [Evidence]
    score: dict[str, Any]  # ScoreBreakdown
    gaps: list[dict[str, Any]]  # [Gap]

    # --- writer / grounding_judge loop
    draft: dict[str, Any]  # Draft
    verdicts: list[dict[str, Any]]  # [Verdict] for the current draft
    revision: int  # how many times the writer has run
    removed: list[dict[str, Any]]  # sentences dropped after the last revision

    # --- human_review / export
    final_draft: dict[str, Any]  # Draft approved by the user
    final_verdicts: list[dict[str, Any]]  # verdicts for sentences the user edited
    review_note: str | None
    approved: bool
    docx_path: str
    application_id: int

    # --- bookkeeping: one entry per node execution (name, seconds, llm calls/tokens)
    trace: Annotated[list[dict[str, Any]], operator.add]
