"""Persistence and dense search for profile chunks."""

from __future__ import annotations

import numpy as np
from sqlalchemy import delete, select, text

from jobfit.db.models import ChunkRow
from jobfit.db.session import get_engine, session_scope
from jobfit.retrieval.embeddings import Embedder
from jobfit.schemas import Chunk


def embedding_text(chunk: Chunk) -> str:
    """What gets embedded / keyword-indexed: the claim plus where it comes from."""
    return f"{chunk.section}: {chunk.text}"


def replace_source(chunks: list[Chunk], source: str, embedder: Embedder) -> int:
    """Delete all chunks of `source` and insert the new ones (re-ingesting is idempotent)."""
    vectors = embedder.embed([embedding_text(c) for c in chunks]) if chunks else []
    with session_scope() as s:
        s.execute(delete(ChunkRow).where(ChunkRow.source == source))
        for c, v in zip(chunks, vectors, strict=True):
            s.add(ChunkRow(**c.model_dump(), embedding=v))
    return len(chunks)


def delete_source(source: str) -> None:
    with session_scope() as s:
        s.execute(delete(ChunkRow).where(ChunkRow.source == source))


def delete_all() -> None:
    with session_scope() as s:
        s.execute(delete(ChunkRow))


def list_chunks(source: str | None = None) -> list[Chunk]:
    with session_scope() as s:
        q = select(ChunkRow).order_by(ChunkRow.source, ChunkRow.id)
        if source:
            q = q.where(ChunkRow.source == source)
        return [_to_chunk(r) for r in s.scalars(q)]


def get_chunks(ids: list[str]) -> dict[str, Chunk]:
    if not ids:
        return {}
    with session_scope() as s:
        rows = s.scalars(select(ChunkRow).where(ChunkRow.id.in_(ids)))
        return {r.id: _to_chunk(r) for r in rows}


def _to_chunk(r: ChunkRow) -> Chunk:
    return Chunk(
        id=r.id,
        source=r.source,
        section=r.section,
        text=r.text,
        date_range=r.date_range,
        tech_tags=list(r.tech_tags or []),
    )


def dense_search(query_vec: np.ndarray, k: int) -> list[tuple[str, float]]:
    """Top-k chunk ids by cosine similarity. Uses pgvector on Postgres, NumPy on SQLite."""
    engine = get_engine()
    if engine.dialect.name == "postgresql":
        vec = "[" + ",".join(f"{x:.6f}" for x in query_vec) + "]"
        sql = text(
            "SELECT id, 1 - (embedding <=> CAST(:q AS vector)) AS sim FROM chunks "
            "WHERE embedding IS NOT NULL ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
        )
        with engine.connect() as conn:
            return [(row.id, float(row.sim)) for row in conn.execute(sql, {"q": vec, "k": k})]

    with session_scope() as s:
        rows = s.execute(select(ChunkRow.id, ChunkRow.embedding)).all()
    rows = [(i, e) for i, e in rows if e is not None]
    if not rows:
        return []
    ids = [i for i, _ in rows]
    matrix = np.vstack([e for _, e in rows])
    sims = matrix @ query_vec  # vectors are normalized, so dot product = cosine similarity
    order = np.argsort(-sims)[:k]
    return [(ids[i], float(sims[i])) for i in order]
