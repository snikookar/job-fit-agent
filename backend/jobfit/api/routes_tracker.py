"""Tracker: the application Kanban."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from jobfit import tracker
from jobfit.db.models import APPLICATION_STATUSES

router = APIRouter(prefix="/api/tracker", tags=["tracker"])


class ApplicationIn(BaseModel):
    title: str
    company: str | None = None
    url: str | None = None


class ApplicationPatch(BaseModel):
    status: str | None = None
    notes: str | None = None


@router.get("")
def list_applications():
    return {"statuses": list(APPLICATION_STATUSES), "applications": tracker.list_applications()}


@router.post("", status_code=201)
def create_application(body: ApplicationIn):
    return tracker.create_application(body.title, body.company, body.url)


@router.patch("/{app_id}")
def update_application(app_id: int, body: ApplicationPatch):
    try:
        app = tracker.update_application(app_id, status=body.status, notes=body.notes)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if app is None:
        raise HTTPException(404, "application not found")
    return app


@router.delete("/{app_id}")
def delete_application(app_id: int):
    if not tracker.delete_application(app_id):
        raise HTTPException(404, "application not found")
    return {"deleted": app_id}


@router.get("/{app_id}/docx")
def download(app_id: int):
    path = tracker.get_docx_path(app_id)
    if not path or not Path(path).exists():
        raise HTTPException(404, "no document for this application")
    return FileResponse(path, filename=Path(path).name)
