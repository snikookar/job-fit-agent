"""Dependencies the nodes need, bundled so tests can swap in fakes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from jobfit.config import Settings, get_settings
from jobfit.llm import LLM, get_judge_llm, get_writer_llm
from jobfit.retrieval.search import HybridRetriever


@dataclass
class Services:
    writer: LLM
    judge: LLM
    settings: Settings = field(default_factory=get_settings)
    # A factory, not an instance: each run takes a fresh snapshot of the profile.
    make_retriever: Callable[[], HybridRetriever] = HybridRetriever

    @classmethod
    def default(cls) -> Services:
        return cls(writer=get_writer_llm(), judge=get_judge_llm())
