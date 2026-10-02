"""FastAPI application.

    uv run uvicorn jobfit.api.main:app --reload --port 8000

There is no authentication: this is a local, single-user tool that holds your resume.
Don't expose it on a public server (see "Privacy" in the README).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jobfit.api import routes_jobs, routes_profile, routes_tracker
from jobfit.api.runs import RunManager, mark_orphaned_runs
from jobfit.config import get_settings
from jobfit.db.session import get_engine, init_db
from jobfit.graph.runner import JobFitAgent
from jobfit.graph.services import Services

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(services: Services | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        mark_orphaned_runs()
        app.state.services = services or Services.default()
        app.state.agent = JobFitAgent(app.state.services)
        app.state.runs = RunManager(app.state.agent)
        yield

    app = FastAPI(
        title="job-fit-agent",
        description="Resume-to-job fit analysis. Every claim is linked to its evidence.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_profile.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_tracker.router)

    @app.get("/api/health", tags=["meta"])
    def health():
        from jobfit.retrieval.embeddings import get_embedder
        from jobfit.retrieval.rerank import get_reranker

        svc: Services = app.state.services
        return {
            "status": "ok",
            "writer": svc.writer.name,
            "judge": svc.judge.name,
            "embedder": get_embedder().name,
            "reranker": get_reranker().name,
            "database": get_engine().dialect.name,
            "offline_mode": "heuristic" in svc.writer.name,
        }

    return app


app = create_app()
