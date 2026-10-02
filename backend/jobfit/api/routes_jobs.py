"""Jobs: start an analysis, stream its progress, review the draft, download the .docx."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from jobfit.db.models import Run
from jobfit.db.session import session_scope
from jobfit.grounding import iter_sentences, judge_draft
from jobfit.retrieval import store
from jobfit.schemas import JOB_EVIDENCE_ID, Draft, ReviewDecision, Verdict

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobIn(BaseModel):
    url: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def one_input(self):
        if not (self.url or "").strip() and not (self.text or "").strip():
            raise ValueError("Provide a job URL or paste the job description.")
        return self


class CheckIn(BaseModel):
    draft: Draft


def _manager(request: Request):
    return request.app.state.runs


def _run_row(run_id: str) -> dict | None:
    with session_scope() as s:
        r = s.get(Run, run_id)
        if r is None:
            return None
        return {
            "run_id": r.thread_id,
            "job_url": r.job_url,
            "title": r.title,
            "company": r.company,
            "status": r.status,
            "score": r.score,
            "error": r.error,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }


@router.post("", status_code=202)
def create_job(job: JobIn, request: Request):
    run_id = uuid.uuid4().hex[:12]
    _manager(request).start(run_id, (job.url or "").strip() or None, (job.text or "").strip() or None)
    return {"run_id": run_id}


@router.get("")
def list_jobs():
    with session_scope() as s:
        rows = s.scalars(select(Run).order_by(Run.created_at.desc()).limit(100)).all()
        ids = [r.thread_id for r in rows]
    return [_run_row(i) for i in ids]


@router.get("/{run_id}")
def get_job(run_id: str, request: Request):
    run = _run_row(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    state = request.app.state.agent.state(run_id) or {}
    # Every chunk the UI may need to show when the user clicks on evidence.
    ids: set[str] = set()
    for items in (state.get("evidence") or {}).values():
        ids |= {e["chunk_id"] for e in items}
    for key in ("draft", "final_draft"):
        if state.get(key):
            ids |= {i for _, _, s in iter_sentences(Draft.model_validate(state[key])) for i in s.evidence_ids}
    for v in state.get("removed") or []:
        ids |= set(v.get("evidence_ids") or [])
    ids.discard(JOB_EVIDENCE_ID)
    chunks = {cid: c.model_dump() for cid, c in store.get_chunks(sorted(ids)).items()}
    return {"run": run, "state": state, "chunks": chunks, "active": _manager(request).is_active(run_id)}


@router.get("/{run_id}/events")
async def job_events(run_id: str, request: Request, after: int = -1):
    if _run_row(run_id) is None:
        raise HTTPException(404, "run not found")
    manager = _manager(request)

    async def stream():
        async for event in manager.subscribe(run_id, after):
            if await request.is_disconnected():
                break
            yield {"event": event["type"], "id": str(event["seq"]), "data": json.dumps(event)}
        yield {"event": "end", "data": "{}"}

    return EventSourceResponse(stream())


@router.post("/{run_id}/check")
def check_draft(run_id: str, body: CheckIn, request: Request):
    """Fact-check an edited draft before approving it (does not resume the run)."""
    state = request.app.state.agent.state(run_id)
    if not state:
        raise HTTPException(404, "run not found")
    previous = [Verdict.model_validate(v) for v in state.get("verdicts") or []]
    judge = request.app.state.services.judge
    threshold = request.app.state.services.settings.judge_threshold
    verdicts = judge_draft(body.draft, state.get("job_text", ""), judge, threshold, cache=previous)
    return [v.model_dump() for v in verdicts]


@router.post("/{run_id}/review", status_code=202)
def review(run_id: str, decision: ReviewDecision, request: Request):
    try:
        _manager(request).resume(run_id, decision)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"run_id": run_id, "resumed": True}


@router.get("/{run_id}/docx")
def download_docx(run_id: str, request: Request):
    state = request.app.state.agent.state(run_id) or {}
    path = state.get("docx_path")
    if not path or not Path(path).exists():
        raise HTTPException(404, "no document for this run (approve the draft first)")
    title = (state.get("requirements") or {}).get("title") or "application"
    safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in title).strip() or "application"
    return FileResponse(
        path,
        filename=f"{safe}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
