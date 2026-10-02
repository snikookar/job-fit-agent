"""The LLM interface used by every graph node.

Nodes only ever ask for *structured* output: "here is a task, return an instance of this
Pydantic model". That single method is easy to implement for a real API, for the offline
heuristic provider, and for scripted fakes in tests.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0

    def add(self, other: Usage) -> None:
        self.calls += other.calls
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.seconds += other.seconds


class LLM(Protocol):
    name: str
    usage: Usage

    def structured(
        self,
        task: str,
        system: str,
        user: str,
        schema: type[T],
        context: dict[str, Any] | None = None,
    ) -> T:
        """Run `task` and return a validated `schema` instance.

        `task` names the step ("parse_requirements", "judge", ...). `context` carries the raw
        inputs; API providers ignore it (they read the prompt), the heuristic provider and
        test fakes use it instead of parsing prompt text.
        """
        ...


class UsageTracker:
    """Thread-safe usage accumulator shared by the provider implementations."""

    def __init__(self) -> None:
        self.usage = Usage()
        self._lock = threading.Lock()

    def record(self, prompt_tokens: int, completion_tokens: int, seconds: float) -> None:
        with self._lock:
            self.usage.add(Usage(1, prompt_tokens, completion_tokens, seconds))
