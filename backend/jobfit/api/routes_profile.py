"""Profile: upload resume/projects, connect GitHub, browse the indexed chunks."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from jobfit.profile import ingest
from jobfit.retrieval import store

router = APIRouter(prefix="/api/profile", tags=["profile"])
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class GitHubRequest(BaseModel):
    target: str  # "username" or "owner/repo, owner/repo2"


class ProfileInfoIn(BaseModel):
    name: str | None = None
    headline: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: str | None = None


async def _read(upload: UploadFile) -> bytes:
    data = await upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"{upload.filename} is larger than 10 MB")
    return data


@router.get("")
def get_profile():
    counts = Counter(c.source for c in store.list_chunks())
    return {
        "info": ingest.get_profile_info(),
        "sources": [{"source": s, "chunks": n} for s, n in sorted(counts.items())],
        "total_chunks": sum(counts.values()),
    }


@router.get("/chunks")
def list_chunks(source: str | None = None):
    return [c.model_dump() for c in store.list_chunks(source)]


@router.get("/chunks/{chunk_id:path}")
def get_chunk(chunk_id: str):
    chunk = store.get_chunks([chunk_id]).get(chunk_id)
    if chunk is None:
        raise HTTPException(404, "chunk not found")
    return chunk.model_dump()


@router.post("/resume")
async def upload_resume(file: UploadFile):
    data = await _read(file)
    try:
        # ingestion is CPU-bound (parsing + embeddings): keep it off the event loop
        from starlette.concurrency import run_in_threadpool

        result = await run_in_threadpool(ingest.ingest_resume, file.filename or "resume.pdf", data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"source": result.source, "chunks": result.chunks}


@router.post("/projects")
async def upload_projects(files: list[UploadFile]):
    from starlette.concurrency import run_in_threadpool

    results = []
    for f in files:
        if not (f.filename or "").lower().endswith((".md", ".markdown", ".txt")):
            raise HTTPException(400, f"{f.filename}: project files must be Markdown (.md)")
        text = (await _read(f)).decode("utf-8", errors="replace")
        r = await run_in_threadpool(ingest.ingest_markdown, f.filename or "project.md", text)
        results.append({"source": r.source, "chunks": r.chunks})
    return results


@router.post("/github")
def connect_github(req: GitHubRequest):
    import httpx

    try:
        results = ingest.ingest_github(req.target)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"GitHub API error: {exc.response.status_code}") from exc
    return [{"source": r.source, "chunks": r.chunks} for r in results]


@router.post("/sample")
def load_sample():
    return [{"source": r.source, "chunks": r.chunks} for r in ingest.load_sample_profile()]


@router.put("/info")
def set_info(info: ProfileInfoIn):
    ingest.set_profile_info(info.model_dump(exclude_none=True))
    return ingest.get_profile_info()


@router.delete("/sources/{source:path}")
def delete_source(source: str):
    store.delete_source(source)
    return {"deleted": source}


@router.delete("")
def delete_profile():
    store.delete_all()
    ingest.set_profile_info({})
    return {"deleted": True}
