"""Scripted LLM for tests: returns canned outputs per task, or delegates to the heuristic."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jobfit.llm.base import T, UsageTracker
from jobfit.llm.heuristic import HANDLERS

Response = dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]


class ScriptedLLM(UsageTracker):
    """`script` maps a task name to a list of responses, consumed in order.

    A response is a dict (returned as-is) or a function of the context. Tasks without a
    script fall back to the heuristic handlers. Every call is recorded in `calls`.
    """

    def __init__(self, script: dict[str, list[Response]] | None = None, name: str = "scripted"):
        super().__init__()
        self.name = name
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    def structured(self, task, system, user, schema: type[T], context=None) -> T:
        ctx = context or {}
        self.calls.append((task, ctx, user))
        self.record(10, 5, 0.0)
        queue = self.script.get(task)
        if queue:
            resp = queue.pop(0) if len(queue) > 1 else queue[0]
            data = resp(ctx) if callable(resp) else resp
        else:
            data = HANDLERS[task](ctx)
        return schema.model_validate(data)

    def tasks(self) -> list[str]:
        return [t for t, _, _ in self.calls]
