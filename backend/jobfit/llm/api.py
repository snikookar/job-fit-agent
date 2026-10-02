"""OpenAI-compatible chat API provider (DeepSeek, GLM, OpenAI, vLLM, Ollama, ...)."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

from pydantic import ValidationError

from jobfit.llm.base import T, UsageTracker

log = logging.getLogger(__name__)


def _openai_client_class():
    """Langfuse's drop-in OpenAI client traces every call, if installed and configured."""
    if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
        try:
            from langfuse.openai import OpenAI  # type: ignore[import-not-found]

            return OpenAI
        except ImportError:
            log.warning("LANGFUSE_* is set but langfuse isn't installed (uv sync --extra tracing)")
    from openai import OpenAI

    return OpenAI


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return m.group(1) if m else text


class OpenAICompatibleLLM(UsageTracker):
    """Structured output via JSON mode + Pydantic validation + one repair attempt.

    Strict `json_schema` response formats aren't supported by every OpenAI-compatible
    provider, but JSON mode is. We put the JSON Schema in the prompt, validate the reply
    with Pydantic and, if it fails, send the validation error back once to be fixed.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        timeout: float = 120.0,
        role: str = "writer",
    ) -> None:
        super().__init__()
        self.name = f"{role}:{model}"
        self.model = model
        self.temperature = temperature
        self.client = _openai_client_class()(base_url=base_url, api_key=api_key, timeout=timeout)

    def structured(
        self,
        task: str,
        system: str,
        user: str,
        schema: type[T],
        context: dict[str, Any] | None = None,
    ) -> T:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": f"{system}\n\nReply with a single JSON object that matches this JSON Schema:\n{schema_json}",
            },
            {"role": "user", "content": user},
        ]
        last_error: Exception | None = None
        for _attempt in range(2):
            content = self._complete(messages, task)
            try:
                return schema.model_validate_json(_strip_fences(content))
            except ValidationError as exc:
                last_error = exc
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": f"That JSON is invalid:\n{exc}\nReturn the corrected JSON only.",
                    },
                ]
        raise ValueError(f"{self.name} returned invalid JSON for task {task!r}: {last_error}")

    def _complete(self, messages: list[dict], task: str) -> str:
        start = time.perf_counter()
        kwargs: dict[str, Any] = {}
        if self.client.__class__.__module__.startswith("langfuse"):
            kwargs["name"] = task  # shows up as the generation name in Langfuse
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            **kwargs,
        )
        u = resp.usage
        self.record(
            u.prompt_tokens if u else 0, u.completion_tokens if u else 0, time.perf_counter() - start
        )
        return resp.choices[0].message.content or ""
