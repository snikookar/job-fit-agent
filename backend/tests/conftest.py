"""Test fixtures: every test gets a fresh SQLite database, offline LLMs and hash embeddings."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from jobfit.config import REPO_DIR, get_settings
from jobfit.db import session as db_session

SAMPLE_PROFILE = REPO_DIR / "sample_profile"


CHECKPOINT_TABLES = (
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
)


def _reset_postgres() -> None:
    """Fresh tables for every test when running against a shared Postgres (CI)."""
    from sqlalchemy import text

    from jobfit.db.models import Base

    engine = db_session.get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        for table in CHECKPOINT_TABLES:
            conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # TEST_DATABASE_URL=postgresql+psycopg://... runs the suite against Postgres + pgvector.
    pg_url = os.environ.get("TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", pg_url or f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("CHECKPOINT_DB", str(tmp_path / "checkpoints.db"))
    monkeypatch.setenv("LLM_PROVIDER", "heuristic")
    monkeypatch.setenv("EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("RERANKER_BACKEND", "lexical")
    monkeypatch.setenv("WRITER_API_KEY", "")
    monkeypatch.setenv("JUDGE_API_KEY", "")
    _clear_caches()
    db_session.reset_engine()
    if pg_url:
        _reset_postgres()
    db_session.init_db()
    yield get_settings()
    db_session.reset_engine()
    _clear_caches()


def _clear_caches() -> None:
    from jobfit.llm import get_judge_llm, get_writer_llm
    from jobfit.retrieval.embeddings import get_embedder
    from jobfit.retrieval.rerank import get_reranker

    get_settings.cache_clear()
    get_writer_llm.cache_clear()
    get_judge_llm.cache_clear()
    get_embedder.cache_clear()
    get_reranker.cache_clear()


@pytest.fixture
def sample_profile():
    """The fictional profile, ingested into the test database."""
    from jobfit.profile.ingest import load_sample_profile

    return load_sample_profile()


@pytest.fixture
def sample_profile_dir() -> Path:
    return SAMPLE_PROFILE
