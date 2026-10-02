"""Profile ingestion: resume + project write-ups + GitHub READMEs -> chunks in the database."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import delete, select

from jobfit.config import REPO_DIR, get_settings
from jobfit.db.models import ProfileInfo
from jobfit.db.session import session_scope
from jobfit.profile import github
from jobfit.profile.chunking import chunk_resume, chunk_sections
from jobfit.profile.parsers import file_to_markdown
from jobfit.retrieval import store
from jobfit.retrieval.embeddings import Embedder, get_embedder

SAMPLE_PROFILE_DIR = REPO_DIR / "sample_profile"


@dataclass
class IngestResult:
    source: str
    chunks: int


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "doc"


def ingest_resume(filename: str, data: bytes, embedder: Embedder | None = None) -> IngestResult:
    md = file_to_markdown(filename, data)
    chunks = chunk_resume(md, source="resume")
    n = store.replace_source(chunks, "resume", embedder or get_embedder())
    return IngestResult("resume", n)


def ingest_markdown(
    name: str, text: str, kind: str = "project", embedder: Embedder | None = None
) -> IngestResult:
    """A project write-up (`kind="project"`) or a GitHub README (`kind="github"`, name=owner/repo)."""
    source = f"github:{name}" if kind == "github" else f"project:{_slug(Path(name).stem)}"
    chunks = chunk_sections(text, source=source)
    n = store.replace_source(chunks, source, embedder or get_embedder())
    return IngestResult(source, n)


def ingest_github(target: str, embedder: Embedder | None = None) -> list[IngestResult]:
    token = get_settings().github_token
    return [
        ingest_markdown(full_name, readme, kind="github", embedder=embedder)
        for full_name, readme in github.fetch_readmes(target, token)
    ]


def load_sample_profile(embedder: Embedder | None = None) -> list[IngestResult]:
    """Load the fictional demo persona from sample_profile/ (replaces the current profile)."""
    embedder = embedder or get_embedder()
    store.delete_all()
    d = SAMPLE_PROFILE_DIR
    results = [ingest_resume("resume.pdf", (d / "resume.pdf").read_bytes(), embedder)]
    for p in sorted((d / "projects").glob("*.md")):
        results.append(ingest_markdown(p.name, p.read_text(encoding="utf-8"), "project", embedder))
    for p in sorted((d / "github").glob("*.md")):
        full_name = p.stem.replace("__", "/", 1)  # files are named owner__repo.md
        results.append(ingest_markdown(full_name, p.read_text(encoding="utf-8"), "github", embedder))
    info = yaml.safe_load((d / "profile.yaml").read_text(encoding="utf-8"))
    set_profile_info(info)
    return results


# --- Contact details for the .docx header -------------------------------------------


def set_profile_info(info: dict) -> None:
    with session_scope() as s:
        s.execute(delete(ProfileInfo))
        for key, value in info.items():
            if value is None:
                continue
            if isinstance(value, list):
                value = " · ".join(str(v) for v in value)
            s.add(ProfileInfo(key=key, value=str(value)))


def get_profile_info() -> dict[str, str]:
    with session_scope() as s:
        return {row.key: row.value for row in s.scalars(select(ProfileInfo))}
