"""High-level API around the compiled graph: start a run, resume it after review, read it.

`start()` and `resume()` yield simple events, so the FastAPI SSE endpoint, the CLI and the
eval scripts all consume the graph the same way.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from jobfit.graph.checkpoint import make_checkpointer
from jobfit.graph.graph import build_graph
from jobfit.graph.services import Services
from jobfit.schemas import ReviewDecision

log = logging.getLogger(__name__)


@dataclass
class RunEvent:
    type: Literal["node", "interrupt", "done", "error"]
    node: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "node": self.node, "data": self.data}


def _summary(node: str, update: dict[str, Any]) -> dict[str, Any]:
    """A small, UI-friendly summary of a node's output (the full state is fetched separately)."""
    out: dict[str, Any] = {"trace": (update.get("trace") or [{}])[-1]}
    if node == "parse_requirements":
        req = update.get("requirements") or {}
        out["title"] = req.get("title")
        out["company"] = req.get("company")
        out["requirements"] = len(req.get("requirements") or [])
    elif node == "match_evidence":
        ev = update.get("evidence") or {}
        out["with_evidence"] = sum(1 for items in ev.values() if items)
    elif node == "score":
        out["score"] = (update.get("score") or {}).get("score")
    elif node == "gap_analysis":
        out["gaps"] = len(update.get("gaps") or [])
    elif node == "writer":
        d = update.get("draft") or {}
        out["round"] = update.get("revision")
        out["sentences"] = len(d.get("bullets") or []) + len(d.get("cover_letter") or [])
    elif node == "grounding_judge":
        v = update.get("verdicts") or []
        out["unsupported"] = sum(1 for x in v if not x["supported"])
        out["removed"] = len(update.get("removed") or [])
    elif node == "export":
        out["application_id"] = update.get("application_id")
        out["docx"] = bool(update.get("docx_path"))
    return out


class JobFitAgent:
    def __init__(
        self, svc: Services | None = None, checkpointer: BaseCheckpointSaver | None = None
    ):
        self.checkpointer = checkpointer or make_checkpointer()
        self.graph = build_graph(svc, self.checkpointer)

    @staticmethod
    def _config(run_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": run_id}, "recursion_limit": 50}

    def start(
        self, run_id: str, job_url: str | None = None, job_text: str | None = None
    ) -> Iterator[RunEvent]:
        inputs = {"run_id": run_id, "job_url": job_url, "job_text_input": job_text, "revision": 0}
        yield from self._stream(inputs, run_id)

    def resume(self, run_id: str, decision: ReviewDecision) -> Iterator[RunEvent]:
        yield from self._stream(Command(resume=decision.model_dump()), run_id)

    def _stream(self, inputs: Any, run_id: str) -> Iterator[RunEvent]:
        config = self._config(run_id)
        try:
            for chunk in self.graph.stream(inputs, config, stream_mode="updates"):
                for node, update in chunk.items():
                    if node == "__interrupt__":
                        yield RunEvent("interrupt", "human_review", {"value": update[0].value})
                    elif isinstance(update, dict):
                        yield RunEvent("node", node, _summary(node, update))
        except (
            Exception
        ) as exc:  # surface node errors as events (e.g. a page that can't be fetched)
            log.exception("run %s failed", run_id)
            snapshot = self.graph.get_state(config)
            failed = snapshot.next[0] if snapshot.next else None
            yield RunEvent("error", failed, {"message": str(exc), "kind": type(exc).__name__})
            return

        if not self.graph.get_state(config).next:
            values = self.state(run_id) or {}
            yield RunEvent(
                "done",
                None,
                {
                    "application_id": values.get("application_id"),
                    "docx": bool(values.get("docx_path")),
                },
            )

    def state(self, run_id: str) -> dict[str, Any] | None:
        snapshot = self.graph.get_state(self._config(run_id))
        if not snapshot.values:
            return None
        values = dict(snapshot.values)
        values["next"] = list(snapshot.next)
        values["awaiting_review"] = "human_review" in snapshot.next
        return values
