"""Pydantic data models shared by the graph, the API and the eval scripts.

The first block mirrors the spec (docs/SPEC.md, section 4). The rest are the
supporting models the pipeline needs to pass results between nodes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --- Job requirements (output of parse_requirements) ----------------------------


class Requirement(BaseModel):
    id: str
    text: str
    category: Literal["skill", "experience", "education", "language", "location", "other"]
    importance: Literal["must", "nice"]
    years: int | None = None


class JobRequirements(BaseModel):
    title: str
    company: str | None = None
    location: str | None = None
    remote: Literal["onsite", "hybrid", "remote", "unknown"] = "unknown"
    visa_sponsorship: Literal["yes", "no", "unknown"] = "unknown"
    requirements: list[Requirement]


# --- Profile ---------------------------------------------------------------------


class Chunk(BaseModel):
    """One retrievable unit of the user's profile: a resume bullet or a README section."""

    id: str
    source: str  # e.g. "resume", "project:rag-chatbot", "github:alex/repo"
    section: str  # e.g. "Experience > Acme GmbH", "Features"
    text: str
    date_range: str | None = None
    tech_tags: list[str] = Field(default_factory=list)


# --- Evidence + scoring ------------------------------------------------------------


class Evidence(BaseModel):
    requirement_id: str
    chunk_id: str
    quote: str
    strength: float = Field(ge=0.0, le=1.0)  # 0..1, from reranker score + LLM assessment
    retrieval_score: float = 0.0
    assessment: Literal["full", "partial", "none"] | None = None


class RequirementScore(BaseModel):
    requirement_id: str
    text: str
    importance: Literal["must", "nice"]
    weight: float
    strength: float
    contribution: float  # weight * strength


class ScoreBreakdown(BaseModel):
    score: float  # 0..100
    must_coverage: float  # share of "must" requirements with enough evidence
    items: list[RequirementScore]


class Gap(BaseModel):
    requirement_id: str
    text: str
    importance: Literal["must", "nice"]
    best_strength: float
    suggestion: str


# --- Drafts + grounding --------------------------------------------------------------


class DraftSentence(BaseModel):
    text: str
    evidence_ids: list[str]


class Draft(BaseModel):
    bullets: list[DraftSentence]
    cover_letter: list[DraftSentence]


class Verdict(BaseModel):
    """The grounding judge's decision on one sentence."""

    section: Literal["bullets", "cover_letter"]
    index: int
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    supported: bool
    p_supported: float
    reason: str
    checks: list[str] = Field(default_factory=list)  # which checks fired (ids, numbers, llm)


#  --- LLM step outputs (internal) -------------------------------------------------------


class Assessment(BaseModel):
    """How well one retrieved chunk supports one requirement."""

    requirement_id: str
    chunk_id: str
    support: Literal["full", "partial", "none"]
    quote: str = ""  # the exact span of the chunk that supports the requirement


class AssessmentList(BaseModel):
    items: list[Assessment]


class GapSuggestion(BaseModel):
    requirement_id: str
    suggestion: str


class GapSuggestionList(BaseModel):
    items: list[GapSuggestion]


class JudgeItem(BaseModel):
    section: Literal["bullets", "cover_letter"]
    index: int
    supported: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class JudgeResult(BaseModel):
    items: list[JudgeItem]


# Sentences about the company or the role (not about the candidate) may cite the job posting.
JOB_EVIDENCE_ID = "job"


class ReviewDecision(BaseModel):
    """What the user sends back from the human review step."""

    approved: bool = True
    draft: Draft | None = None  # edited draft; None means "approve as is"
    # Edited sentences are fact-checked again; unsupported ones are removed unless this is set.
    keep_unsupported_edits: bool = False
    note: str | None = None
