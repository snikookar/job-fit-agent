"""Hybrid retrieval over the profile: BM25 + dense, fused with RRF, then reranked.

Why hybrid: job requirements mix exact terms ("Terraform", "pgvector") that keyword search
nails, and paraphrases ("shipped LLM features" vs "built a RAG assistant") that only dense
embeddings catch. Reciprocal rank fusion combines both rankings without having to calibrate
their scores against each other. The cross-encoder reranker then picks the best few.
"""

from __future__ import annotations

from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from jobfit.config import get_settings
from jobfit.retrieval import store
from jobfit.retrieval.embeddings import Embedder, get_embedder
from jobfit.retrieval.rerank import Reranker, get_reranker
from jobfit.schemas import Chunk
from jobfit.textutil import STOPWORDS, stem, tokenize

RRF_K = 60  # standard constant from the RRF paper (Cormack et al., 2009)


@dataclass
class Hit:
    chunk: Chunk
    score: float  # reranker score, 0..1
    fused: float  # RRF score before reranking


def _bm25_tokens(text: str) -> list[str]:
    return [stem(t) for t in tokenize(text) if t not in STOPWORDS]


class HybridRetriever:
    """Loads a snapshot of the profile once, then answers many queries against it."""

    def __init__(self, embedder: Embedder | None = None, reranker: Reranker | None = None) -> None:
        self.embedder = embedder or get_embedder()
        self.reranker = reranker or get_reranker()
        self.chunks = store.list_chunks()
        self.by_id = {c.id: c for c in self.chunks}
        corpus = [_bm25_tokens(store.embedding_text(c)) for c in self.chunks]
        self.bm25 = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, k: int | None = None, candidates: int | None = None) -> list[Hit]:
        s = get_settings()
        k = k or s.evidence_top_k
        candidates = candidates or s.retrieval_candidates
        if not self.chunks:
            return []

        # 1) keyword ranking
        bm25_scores = self.bm25.get_scores(_bm25_tokens(query)) if self.bm25 else []
        bm25_ranked = sorted(
            (i for i, sc in enumerate(bm25_scores) if sc > 0), key=lambda i: -bm25_scores[i]
        )[:candidates]
        # 2) dense ranking
        qvec = self.embedder.embed([query])[0]
        dense_ranked = [cid for cid, _ in store.dense_search(qvec, candidates)]

        # 3) reciprocal rank fusion
        fused: dict[str, float] = {}
        for rank, i in enumerate(bm25_ranked):
            cid = self.chunks[i].id
            fused[cid] = fused.get(cid, 0.0) + 1 / (RRF_K + rank + 1)
        for rank, cid in enumerate(dense_ranked):
            if cid in self.by_id:
                fused[cid] = fused.get(cid, 0.0) + 1 / (RRF_K + rank + 1)
        pool = sorted(fused, key=lambda c: -fused[c])[:candidates]
        if not pool:
            return []

        # 4) rerank
        passages = [store.embedding_text(self.by_id[c]) for c in pool]
        scores = self.reranker.score(query, passages)
        hits = [Hit(self.by_id[c], float(sc), fused[c]) for c, sc in zip(pool, scores, strict=True)]
        hits.sort(key=lambda h: (-h.score, -h.fused))
        return hits[:k]
