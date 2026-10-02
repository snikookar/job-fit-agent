"""Rerankers: score (query, passage) pairs on a 0..1 scale.

- `BgeReranker`: BAAI/bge-reranker-v2-m3 cross-encoder. Reads query and passage together,
  so it is much more precise than comparing two separately computed embeddings.
- `LexicalReranker`: share of the query's content words (and tech tags) found in the
  passage. Fallback when the `ml` extra isn't installed.
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from typing import Protocol

from jobfit.config import get_settings
from jobfit.profile.tech_tags import extract_tech_tags
from jobfit.textutil import content_terms

log = logging.getLogger(__name__)


class Reranker(Protocol):
    name: str

    def score(self, query: str, passages: list[str]) -> list[float]: ...


class LexicalReranker:
    name = "lexical"

    def score(self, query: str, passages: list[str]) -> list[float]:
        q_terms = content_terms(query)
        q_tags = set(extract_tech_tags(query))
        scores = []
        for p in passages:
            p_terms = content_terms(p)
            term_score = len(q_terms & p_terms) / len(q_terms) if q_terms else 0.0
            if q_tags:
                tag_score = len(q_tags & set(extract_tech_tags(p))) / len(q_tags)
                scores.append(0.5 * term_score + 0.5 * tag_score)
            else:
                scores.append(term_score)
        return scores


class BgeReranker:
    name = "bge"

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        log.info("loading reranker %s (first run downloads ~2 GB)", model_name)
        self.model = CrossEncoder(model_name)

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        raw = self.model.predict([(query, p) for p in passages])
        values = [float(x) for x in raw]
        # Depending on the sentence-transformers version the output is a logit or a probability.
        if any(v < 0 or v > 1 for v in values):
            values = [1 / (1 + math.exp(-v)) for v in values]
        return values


@lru_cache
def get_reranker() -> Reranker:
    s = get_settings()
    backend = s.reranker_backend
    if backend == "auto":
        from jobfit.retrieval.embeddings import _ml_available

        backend = "bge" if _ml_available() else "lexical"
    if backend == "bge":
        return BgeReranker(s.reranker_model)
    return LexicalReranker()
