"""Text embedders.

- `BgeM3Embedder`: BAAI/bge-m3 via sentence-transformers. Multilingual (useful for German
  postings against an English resume), 1024 dimensions, 8k token context.
- `HashEmbedder`: deterministic feature hashing of words and word pairs. No model download,
  used in tests/CI and as the fallback when the `ml` extra isn't installed. It only captures
  lexical overlap, so semantic recall is lower.
"""

from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from typing import Protocol

import numpy as np

from jobfit.config import get_settings
from jobfit.textutil import STOPWORDS, stem, tokenize

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return L2-normalized vectors, shape (len(texts), dim)."""
        ...


class HashEmbedder:
    name = "hash"

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def _bucket(self, feature: str) -> tuple[int, float]:
        h = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        n = int.from_bytes(h, "little")
        return n % self.dim, 1.0 if (n >> 63) & 1 else -1.0

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            words = [stem(t) for t in tokenize(text) if t not in STOPWORDS]
            feats = words + [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
            for f in feats:
                j, sign = self._bucket(f)
                out[i, j] += sign
            norm = np.linalg.norm(out[i])
            if norm > 0:
                out[i] /= norm
        return out


class BgeM3Embedder:
    name = "bge-m3"
    dim = 1024

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        log.info("loading embedding model %s (first run downloads ~2 GB)", model_name)
        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self.model.encode(texts, normalize_embeddings=True, batch_size=16)
        return np.asarray(vecs, dtype=np.float32)


def _ml_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    backend = s.embedding_backend
    if backend == "auto":
        backend = "bge-m3" if _ml_available() else "hash"
        if backend == "hash":
            log.warning("sentence-transformers not installed: using HashEmbedder (lexical only)")
    if backend == "bge-m3":
        return BgeM3Embedder(s.embedding_model)
    return HashEmbedder(s.embedding_dim)
