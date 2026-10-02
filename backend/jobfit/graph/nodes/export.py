"""export: write the approved draft to .docx and log the application in the tracker."""

from __future__ import annotations

from pathlib import Path

from jobfit import tracker
from jobfit.graph.nodes._common import traced
from jobfit.graph.services import Services
from jobfit.graph.state import JobFitState
from jobfit.profile.ingest import get_profile_info
from jobfit.schemas import Draft, JobRequirements


@traced("export")
def export(state: JobFitState, svc: Services) -> dict:
    from jobfit.export.docx import build_docx

    job = JobRequirements.model_validate(state["requirements"])
    run_id = state.get("run_id") or "run"
    docx_path: str | None = None

    if state.get("approved"):
        final = Draft.model_validate(state["final_draft"])
        path = build_docx(
            final,
            job,
            get_profile_info(),
            Path(svc.settings.export_dir) / f"{run_id}.docx",
            language=state.get("language", "en"),
            template=svc.settings.export_template,
        )
        docx_path = str(path)

    # A rejected draft still lands in the tracker as "saved", just without a document.
    app_id = tracker.upsert_from_run(
        run_id,
        title=job.title,
        company=job.company,
        url=state.get("job_url"),
        location=job.location,
        score=(state.get("score") or {}).get("score"),
        docx_path=docx_path,
    )
    out: dict = {"application_id": app_id}
    if docx_path:
        out["docx_path"] = docx_path
    return out
