"""Test fixtures: every test gets a fresh SQLite database, offline LLMs and hash embeddings."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobfit.config import REPO_DIR, get_settings
from jobfit.db import session as db_session

SAMPLE_PROFILE = REPO_DIR / "sample_profile"


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("LLM_PROVIDER", "heuristic")
    monkeypatch.setenv("EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("RERANKER_BACKEND", "lexical")
    monkeypatch.setenv("WRITER_API_KEY", "")
    monkeypatch.setenv("JUDGE_API_KEY", "")
    get_settings.cache_clear()
    db_session.reset_engine()
    db_session.init_db()
    yield get_settings()
    db_session.reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def sample_profile_dir() -> Path:
    return SAMPLE_PROFILE
