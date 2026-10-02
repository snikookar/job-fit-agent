"""Application settings, loaded from environment variables and an optional `.env` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Storage ---------------------------------------------------------------
    # SQLite works out of the box; set a postgresql+psycopg:// URL to use pgvector.
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'jobfit.db').as_posix()}"
    export_dir: Path = BACKEND_DIR / "data" / "exports"

    # --- LLMs ------------------------------------------------------------------
    # "auto": use the API if a key is set, otherwise the offline heuristic provider.
    llm_provider: Literal["auto", "api", "heuristic"] = "auto"

    # Writer (and the extraction / assessment steps). Default: DeepSeek.
    writer_base_url: str = "https://api.deepseek.com"
    writer_api_key: str = ""
    writer_model: str = "deepseek-chat"

    # Judge: deliberately a *different* model family, so it doesn't share the writer's
    # blind spots. Default: Zhipu GLM.
    judge_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"
    judge_api_key: str = ""
    judge_model: str = "glm-4.6"

    llm_temperature: float = 0.2
    llm_timeout_s: float = 120.0

    # --- Retrieval -------------------------------------------------------------
    embedding_backend: Literal["auto", "bge-m3", "hash"] = "auto"
    reranker_backend: Literal["auto", "bge", "lexical"] = "auto"
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    embedding_dim: int = 1024
    retrieval_candidates: int = 20  # fused BM25 + dense candidates sent to the reranker
    evidence_top_k: int = 3  # evidence kept per requirement

    # --- Agent behaviour -------------------------------------------------------
    max_revisions: int = 2  # writer <-> judge loop limit
    # A sentence counts as supported when P(supported) from the judge >= this value.
    # Raise it to be stricter, lower it if the false alarm rate is too high.
    judge_threshold: float = 0.5
    # Evidence strength below this marks a requirement as a gap.
    gap_threshold: float = 0.5

    # --- Fetching --------------------------------------------------------------
    fetch_timeout_s: float = 20.0
    use_playwright: bool = True  # only used if the `browser` extra is installed

    # --- API -------------------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:3000"]
    github_token: str = ""  # optional; raises the GitHub API rate limit

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")


@lru_cache
def get_settings() -> Settings:
    return Settings()
