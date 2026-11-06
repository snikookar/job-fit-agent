"""MCP server: the agent's read-only capabilities as Model Context Protocol tools.

uv run jobfit-mcp            # stdio transport, for Claude Code / Claude Desktop

Tools (all read-only; none of them writes to the profile, the tracker or the runs):
  search_profile      hybrid search (BM25 + dense + rerank) over the indexed profile
  score_job           requirements, evidence, fit score and gaps for a pasted posting
  check_claim         the three-layer fact-check on one sentence and its citations
  list_tracker_cards  the application tracker, optionally filtered by status

Tool arguments come from a model, which may have read a hostile web page, so they are
treated as untrusted: every argument has a size limit, the job is text only (the server
never fetches a URL it was given), and errors are reported without internals.
See docs/phases/11-mcp-server.md for the design choices.
"""

from __future__ import annotations

import logging
import sys
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from jobfit import tracker
from jobfit.db.models import APPLICATION_STATUSES
from jobfit.fetching import FetchError
from jobfit.graph.nodes.fetch_job import MAX_JOB_CHARS, fetch_job
from jobfit.graph.nodes.gap_analysis import gap_analysis
from jobfit.graph.nodes.match_evidence import match_evidence
from jobfit.graph.nodes.parse_requirements import parse_requirements
from jobfit.graph.nodes.score import score
from jobfit.graph.services import Services
from jobfit.grounding import judge_draft
from jobfit.retrieval import store
from jobfit.schemas import (
    JOB_EVIDENCE_ID,
    Chunk,
    Draft,
    DraftSentence,
    Evidence,
    Gap,
    JobRequirements,
    ScoreBreakdown,
    Verdict,
)

MAX_QUERY_CHARS = 500
MAX_SENTENCE_CHARS = 1_000
MAX_EVIDENCE_IDS = 10
# The same nodes the graph runs, up to (not including) the writer.
SCORING_NODES = (fetch_job, parse_requirements, match_evidence, score, gap_analysis)

INSTRUCTIONS = """\
Tools over the user's job-fit-agent profile (resume, projects, GitHub READMEs).
- search_profile finds evidence; its chunk ids are what check_claim expects as citations.
- score_job takes the *text* of a job posting (fetch the page yourself and paste it).
- check_claim fact-checks one resume bullet or cover-letter sentence against its citations.
- list_tracker_cards shows the application tracker.
All tools are read-only. The profile is edited in the web app or with the `jobfit` CLI."""

READ_ONLY_LOCAL = ToolAnnotations(read_only_hint=True, open_world_hint=False)
# score_job and check_claim call the configured LLM APIs (unless in offline mode).
READ_ONLY_LLM = ToolAnnotations(read_only_hint=True, open_world_hint=True)


class SearchHit(BaseModel):
    chunk: Chunk
    score: float  # reranker score, 0..1


class FitReport(BaseModel):
    offline_mode: bool  # True: rule-based stand-ins for the LLMs, not real model output
    language: str
    job: JobRequirements
    score: ScoreBreakdown
    evidence: dict[str, list[Evidence]]  # requirement_id -> evidence, strongest first
    gaps: list[Gap]


class TrackerCards(BaseModel):
    statuses: list[str]
    cards: list[dict[str, Any]]


def _require_profile() -> None:
    if not store.list_chunks():
        raise ToolError(
            "The profile is empty. Add a resume in the web app (Profile page) "
            "or run `uv run jobfit load-sample` for the demo profile."
        )


def create_server(svc: Services | None = None) -> MCPServer:
    """Build the server. Tests pass their own Services (offline LLMs, scripted judges)."""
    svc = svc or Services.default()
    server = MCPServer("jobfit", instructions=INSTRUCTIONS)

    @server.tool(annotations=READ_ONLY_LOCAL)
    def search_profile(
        query: Annotated[str, Field(min_length=1, max_length=MAX_QUERY_CHARS)],
        k: Annotated[int, Field(ge=1, le=10)] = 5,
    ) -> list[SearchHit]:
        """Search the user's profile for evidence of a skill or experience.

        Hybrid retrieval: BM25 keyword search + dense embeddings, fused with reciprocal
        rank fusion and reranked by a cross-encoder. Returns profile chunks (resume
        bullets, project and README sections) with their ids and a 0..1 relevance score.
        Relevance is not proof: use check_claim to verify a sentence against a chunk.
        """
        if not query.strip():
            raise ToolError("query is blank")
        hits = svc.make_retriever().search(query, k=k)
        return [SearchHit(chunk=h.chunk, score=round(h.score, 4)) for h in hits]

    @server.tool(annotations=READ_ONLY_LLM)
    def score_job(
        job_text: Annotated[str, Field(min_length=50, max_length=MAX_JOB_CHARS)],
    ) -> FitReport:
        """Score a job posting against the user's profile.

        Pass the posting's text, not a URL. Runs the agent's analysis steps: extract the
        requirements, find and assess evidence for each one, compute the deterministic
        fit score (must = weight 2, nice = weight 1) and list the gaps. Nothing is saved:
        this does not create a run, a draft or a tracker card.
        """
        _require_profile()
        state: dict[str, Any] = {"job_text_input": job_text}
        try:
            for node in SCORING_NODES:
                out = node(state, svc)
                out.pop("trace", None)
                state.update(out)
        except (FetchError, ValueError) as exc:  # too short, no requirements found
            raise ToolError(str(exc)) from exc
        return FitReport(
            offline_mode="heuristic" in svc.writer.name,
            language=state["language"],
            job=JobRequirements.model_validate(state["requirements"]),
            score=ScoreBreakdown.model_validate(state["score"]),
            evidence={
                rid: [Evidence.model_validate(e) for e in items]
                for rid, items in state["evidence"].items()
            },
            gaps=[Gap.model_validate(g) for g in state["gaps"]],
        )

    @server.tool(annotations=READ_ONLY_LLM)
    def check_claim(
        sentence: Annotated[str, Field(min_length=1, max_length=MAX_SENTENCE_CHARS)],
        evidence_ids: Annotated[
            list[Annotated[str, Field(min_length=1, max_length=200)]],
            Field(max_length=MAX_EVIDENCE_IDS),
        ],
        section: Literal["bullets", "cover_letter"] = "bullets",
        job_text: Annotated[str | None, Field(max_length=MAX_JOB_CHARS)] = None,
    ) -> Verdict:
        """Fact-check one sentence against the profile chunks it cites.

        The same three layers the agent uses on its own drafts: (1) citations exist and a
        resume bullet cites the profile, (2) every number in the sentence appears in the
        cited evidence, (3) an LLM judge decides whether the evidence supports the claim.
        `evidence_ids` are chunk ids from search_profile; a cover-letter sentence about
        the company may cite "job", in which case pass the posting as `job_text`.
        """
        if JOB_EVIDENCE_ID in evidence_ids and not (job_text or "").strip():
            raise ToolError('The sentence cites "job": pass the posting as job_text.')
        s = DraftSentence(text=sentence, evidence_ids=evidence_ids)
        draft = (
            Draft(bullets=[s], cover_letter=[])
            if section == "bullets"
            else Draft(bullets=[], cover_letter=[s])
        )
        (verdict,) = judge_draft(draft, job_text or "", svc.judge, svc.settings.judge_threshold)
        return verdict

    @server.tool(annotations=READ_ONLY_LOCAL)
    def list_tracker_cards(
        status: Literal[APPLICATION_STATUSES] | None = None,
    ) -> TrackerCards:
        """List the cards on the application tracker (Saved -> Applied -> Interview -> Offer /
        Rejected), most recently updated first, optionally only those with one status."""
        cards = tracker.list_applications()
        if status is not None:
            cards = [c for c in cards if c["status"] == status]
        return TrackerCards(statuses=list(APPLICATION_STATUSES), cards=cards)

    return server


def main() -> None:
    # stdout carries the protocol: logs (and the "offline mode" warnings) go to stderr.
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    from jobfit.db.session import init_db

    init_db()
    create_server().run("stdio")


if __name__ == "__main__":
    main()
