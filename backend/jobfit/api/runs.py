"""Background execution of graph runs + an event log per run for Server-Sent Events.

A run executes in a worker thread (the graph and the LLM clients are synchronous). Each
event is appended to an in-memory log with a sequence number; SSE clients read the log
from any position (`?after=N`), so a page reload or a second tab can catch up. Run
status is also written to the `runs` table, and the full state lives in the LangGraph
checkpoint, so nothing important is lost if the in-memory log is.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Iterator
from typing import Any

from sqlalchemy import select, update

from jobfit.db.models import Run
from jobfit.db.session import session_scope
from jobfit.graph.runner import JobFitAgent, RunEvent
from jobfit.schemas import ReviewDecision

log = logging.getLogger(__name__)
TERMINAL = {"interrupt", "done", "error"}


class RunManager:
    def __init__(self, agent: JobFitAgent) -> None:
        self.agent = agent
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._active: set[str] = set()
        self._lock = threading.Lock()

    # --- lifecycle -------------------------------------------------------------------

    def start(self, run_id: str, job_url: str | None, job_text: str | None) -> None:
        with session_scope() as s:
            s.add(Run(thread_id=run_id, job_url=job_url, status="running"))
        self._launch(run_id, self.agent.start(run_id, job_url=job_url, job_text=job_text))

    def resume(self, run_id: str, decision: ReviewDecision) -> None:
        with self._lock:
            if run_id in self._active:
                raise RuntimeError("This run is still in progress.")
        state = self.agent.state(run_id)
        if not state or not state.get("awaiting_review"):
            raise RuntimeError("This run is not waiting for review.")
        self._set_status(run_id, status="running")
        self._launch(run_id, self.agent.resume(run_id, decision))

    def _launch(self, run_id: str, events: Iterator[RunEvent]) -> None:
        with self._lock:
            self._active.add(run_id)
            self._events.setdefault(run_id, [])
        threading.Thread(target=self._consume, args=(run_id, events), daemon=True, name=f"run-{run_id}").start()

    def _consume(self, run_id: str, events: Iterator[RunEvent]) -> None:
        try:
            for e in events:
                self._append(run_id, e.to_dict())
                self._record(run_id, e)
        except Exception as exc:  # pragma: no cover - the runner already converts node errors
            log.exception("run %s crashed", run_id)
            self._append(run_id, {"type": "error", "node": None, "data": {"message": str(exc)}})
            self._set_status(run_id, status="failed", error=str(exc))
        finally:
            with self._lock:
                self._active.discard(run_id)

    def _append(self, run_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            log_ = self._events.setdefault(run_id, [])
            event["seq"] = len(log_)
            log_.append(event)

    def _record(self, run_id: str, e: RunEvent) -> None:
        if e.type == "node" and e.node == "parse_requirements":
            self._set_status(run_id, title=e.data.get("title"), company=e.data.get("company"))
        elif e.type == "node" and e.node == "score":
            self._set_status(run_id, score=e.data.get("score"))
        elif e.type == "interrupt":
            self._set_status(run_id, status="awaiting_review")
        elif e.type == "done":
            self._set_status(run_id, status="done")
        elif e.type == "error":
            self._set_status(run_id, status="failed", error=e.data.get("message"))

    @staticmethod
    def _set_status(run_id: str, **fields: Any) -> None:
        with session_scope() as s:
            s.execute(update(Run).where(Run.thread_id == run_id).values(**fields))

    # --- reading ---------------------------------------------------------------------

    def is_active(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._active

    def events(self, run_id: str, after: int = -1) -> list[dict[str, Any]]:
        with self._lock:
            return [e for e in self._events.get(run_id, []) if e["seq"] > after]

    async def subscribe(self, run_id: str, after: int = -1, poll_s: float = 0.15) -> AsyncIterator[dict[str, Any]]:
        """Yield events after `after` until the run pauses, finishes or fails."""
        while True:
            new = self.events(run_id, after)
            for e in new:
                after = e["seq"]
                yield e
            if new and new[-1]["type"] in TERMINAL and not self.is_active(run_id):
                return
            if not new and not self.is_active(run_id):
                return  # nothing running and nothing new: the stream is over
            await asyncio.sleep(poll_s)


def mark_orphaned_runs() -> None:
    """Runs that were 'running' when the server stopped can't continue: mark them failed."""
    with session_scope() as s:
        for run in s.scalars(select(Run).where(Run.status == "running")):
            run.status = "failed"
            run.error = "The server restarted while this run was in progress. Please start it again."
