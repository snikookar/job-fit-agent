"""fetch_job: URL or pasted text -> clean job text + language."""

from __future__ import annotations

from jobfit.fetching import FetchError, fetch_url, from_pasted_text
from jobfit.graph.nodes._common import traced
from jobfit.graph.services import Services
from jobfit.graph.state import JobFitState

MAX_JOB_CHARS = 20_000


@traced("fetch_job")
def fetch_job(state: JobFitState, svc: Services) -> dict:
    pasted = (state.get("job_text_input") or "").strip()
    url = (state.get("job_url") or "").strip()
    if pasted:
        job = from_pasted_text(pasted)  # pasted text always wins: it's the reliable path
        job.url = url or None
    elif url:
        job = fetch_url(url)
    else:
        raise FetchError("Provide a job URL or paste the job description.")

    return {
        "job_text": job.text[:MAX_JOB_CHARS],
        "job_source": job.source,
        "language": job.language,
        "job_hints": {"title": job.title, "company": job.company, "location": job.location},
    }
