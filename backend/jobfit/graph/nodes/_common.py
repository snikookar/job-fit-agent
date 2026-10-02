"""Shared node wrapper: records duration and LLM usage for each node run."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from functools import wraps
from typing import Any

from jobfit.graph.services import Services
from jobfit.graph.state import JobFitState

NodeFn = Callable[[JobFitState, Services], dict[str, Any]]


def traced(name: str) -> Callable[[NodeFn], NodeFn]:
    def deco(fn: NodeFn) -> NodeFn:
        @wraps(fn)
        def wrapper(state: JobFitState, svc: Services) -> dict[str, Any]:
            before = [replace(svc.writer.usage), replace(svc.judge.usage)]
            start = time.perf_counter()
            out = dict(fn(state, svc))
            after = [svc.writer.usage, svc.judge.usage]
            calls = sum(a.calls - b.calls for a, b in zip(after, before, strict=True))
            tokens = sum(
                (a.prompt_tokens + a.completion_tokens) - (b.prompt_tokens + b.completion_tokens)
                for a, b in zip(after, before, strict=True)
            )
            out["trace"] = [
                {
                    "node": name,
                    "seconds": round(time.perf_counter() - start, 3),
                    "llm_calls": calls,
                    "tokens": tokens,
                }
            ]
            return out

        return wrapper

    return deco
