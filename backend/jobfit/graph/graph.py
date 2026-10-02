"""The LangGraph graph (see docs/SPEC.md, section 3).

fetch_job -> parse_requirements -> match_evidence -> score -> gap_analysis
  -> writer -> grounding_judge --(unsupported, rounds left)--> writer
                               --(ok)--> human_review [interrupt] -> export -> END
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from jobfit.graph.nodes.export import export
from jobfit.graph.nodes.fetch_job import fetch_job
from jobfit.graph.nodes.gap_analysis import gap_analysis
from jobfit.graph.nodes.grounding_judge import grounding_judge, route_after_judge
from jobfit.graph.nodes.human_review import human_review
from jobfit.graph.nodes.match_evidence import match_evidence
from jobfit.graph.nodes.parse_requirements import parse_requirements
from jobfit.graph.nodes.score import score
from jobfit.graph.nodes.writer import writer
from jobfit.graph.services import Services
from jobfit.graph.state import JobFitState

NODES = {
    "fetch_job": fetch_job,
    "parse_requirements": parse_requirements,
    "match_evidence": match_evidence,
    "score": score,
    "gap_analysis": gap_analysis,
    "writer": writer,
    "grounding_judge": grounding_judge,
    "human_review": human_review,
    "export": export,
}
NODE_ORDER = list(NODES)


def build_graph(svc: Services | None = None, checkpointer: BaseCheckpointSaver | None = None):
    svc = svc or Services.default()
    g = StateGraph(JobFitState)
    for name, fn in NODES.items():
        # Bind the services; LangGraph only passes the state.
        g.add_node(name, lambda state, fn=fn: fn(state, svc))

    g.add_edge(START, "fetch_job")
    g.add_edge("fetch_job", "parse_requirements")
    g.add_edge("parse_requirements", "match_evidence")
    g.add_edge("match_evidence", "score")
    g.add_edge("score", "gap_analysis")
    g.add_edge("gap_analysis", "writer")
    g.add_edge("writer", "grounding_judge")
    g.add_conditional_edges(
        "grounding_judge", route_after_judge, {"writer": "writer", "human_review": "human_review"}
    )
    g.add_edge("human_review", "export")
    g.add_edge("export", END)
    return g.compile(checkpointer=checkpointer)
