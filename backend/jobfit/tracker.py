"""Application tracker (the Kanban): Saved -> Applied -> Interview -> Offer / Rejected."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from jobfit.db.models import APPLICATION_STATUSES, Application
from jobfit.db.session import session_scope


def _to_dict(a: Application) -> dict[str, Any]:
    return {
        "id": a.id,
        "run_thread_id": a.run_thread_id,
        "title": a.title,
        "company": a.company,
        "url": a.url,
        "location": a.location,
        "status": a.status,
        "score": a.score,
        "has_docx": bool(a.docx_path),
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def upsert_from_run(
    run_thread_id: str,
    title: str,
    company: str | None,
    url: str | None,
    location: str | None,
    score: float | None,
    docx_path: str | None,
) -> int:
    """Create the tracker card for a run, or update it if the run is exported again."""
    with session_scope() as s:
        app = s.scalars(select(Application).where(Application.run_thread_id == run_thread_id)).first()
        if app is None:
            app = Application(run_thread_id=run_thread_id, title=title, status="saved")
            s.add(app)
        app.title, app.company, app.url, app.location = title, company, url, location
        app.score, app.docx_path = score, docx_path
        s.flush()
        return app.id


def list_applications() -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.scalars(select(Application).order_by(Application.updated_at.desc()))
        return [_to_dict(a) for a in rows]


def get_application(app_id: int) -> dict[str, Any] | None:
    with session_scope() as s:
        a = s.get(Application, app_id)
        return _to_dict(a) if a else None


def get_docx_path(app_id: int) -> str | None:
    with session_scope() as s:
        a = s.get(Application, app_id)
        return a.docx_path if a else None


def create_application(title: str, company: str | None = None, url: str | None = None) -> dict[str, Any]:
    with session_scope() as s:
        a = Application(title=title, company=company, url=url, status="saved")
        s.add(a)
        s.flush()
        return _to_dict(a)


def update_application(app_id: int, status: str | None = None, notes: str | None = None) -> dict[str, Any] | None:
    if status is not None and status not in APPLICATION_STATUSES:
        raise ValueError(f"status must be one of {APPLICATION_STATUSES}")
    with session_scope() as s:
        a = s.get(Application, app_id)
        if a is None:
            return None
        if status is not None:
            a.status = status
        if notes is not None:
            a.notes = notes
        s.flush()
        return _to_dict(a)


def delete_application(app_id: int) -> bool:
    with session_scope() as s:
        a = s.get(Application, app_id)
        if a is None:
            return False
        s.delete(a)
        return True
