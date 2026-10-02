"""LLM providers. `get_writer_llm()` / `get_judge_llm()` pick one based on settings."""

from __future__ import annotations

import logging
from functools import lru_cache

from jobfit.config import get_settings
from jobfit.llm.base import LLM, Usage
from jobfit.llm.heuristic import HeuristicLLM

log = logging.getLogger(__name__)

__all__ = ["LLM", "Usage", "get_writer_llm", "get_judge_llm"]


def _use_api(api_key: str) -> bool:
    provider = get_settings().llm_provider
    if provider == "heuristic":
        return False
    if provider == "api" and not api_key:
        raise RuntimeError("LLM_PROVIDER=api but no API key is configured")
    return bool(api_key)


@lru_cache
def get_writer_llm() -> LLM:
    s = get_settings()
    if not _use_api(s.writer_api_key):
        log.warning("No WRITER_API_KEY: using the offline heuristic provider")
        return HeuristicLLM("writer")
    from jobfit.llm.api import OpenAICompatibleLLM

    return OpenAICompatibleLLM(
        s.writer_base_url,
        s.writer_api_key,
        s.writer_model,
        s.llm_temperature,
        s.llm_timeout_s,
        "writer",
    )


@lru_cache
def get_judge_llm() -> LLM:
    s = get_settings()
    from jobfit.llm.api import OpenAICompatibleLLM

    if _use_api(s.judge_api_key):
        # temperature 0: the judge should be as repeatable as possible
        return OpenAICompatibleLLM(
            s.judge_base_url, s.judge_api_key, s.judge_model, 0.0, s.llm_timeout_s, "judge"
        )
    if _use_api(s.writer_api_key):
        log.warning(
            "No JUDGE_API_KEY: the judge falls back to the writer's model. Use a different "
            "model family for the judge so it doesn't share the writer's blind spots."
        )
        return OpenAICompatibleLLM(
            s.writer_base_url, s.writer_api_key, s.writer_model, 0.0, s.llm_timeout_s, "judge"
        )
    return HeuristicLLM("judge")
