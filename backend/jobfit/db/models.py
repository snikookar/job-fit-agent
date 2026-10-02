"""SQLAlchemy models: profile chunks, profile info, analysis runs and the application tracker.

LangGraph checkpoints live in their own tables, created by the checkpointer itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

EMBEDDING_DIM = 1024  # bge-m3 output size; the hash embedder matches it


def utcnow() -> datetime:
    return datetime.now(UTC)


class EmbeddingType(TypeDecorator):
    """A `vector(N)` column on PostgreSQL (pgvector), a JSON array on SQLite.

    This keeps one model definition for both databases: Postgres runs the similarity
    search in SQL, SQLite falls back to NumPy in Python (fine for a few thousand chunks).
    """

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return None
        return [float(x) for x in value]

    def process_result_value(self, value: Any, dialect):
        if value is None:
            return None
        return np.asarray(value, dtype=np.float32)


class Base(DeclarativeBase):
    pass


class ChunkRow(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    source: Mapped[str] = mapped_column(String(255), index=True)
    section: Mapped[str] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)
    date_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tech_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    embedding: Mapped[Any] = mapped_column(EmbeddingType(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProfileInfo(Base):
    """Key/value contact details used in the exported .docx header (name, email, links...)."""

    __tablename__ = "profile_info"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Run(Base):
    """One job analysis. `thread_id` is also the LangGraph thread id for its checkpoints."""

    __tablename__ = "runs"

    thread_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # running | awaiting_review | done | failed
    status: Mapped[str] = mapped_column(String(32), default="running")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


APPLICATION_STATUSES = ("saved", "applied", "interview", "offer", "rejected")


class Application(Base):
    """A row in the tracker Kanban."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str | None] = mapped_column(String(500), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="saved")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    docx_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
