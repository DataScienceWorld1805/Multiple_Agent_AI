"""HTTP API + static UI for the research-synthesis agent."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import get_settings
from src.graph.build_graph import build_graph
from src.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    query: str
    created_at: str
    updated_at: str
    stage: str | None = None
    error: str | None = None
    plan: dict[str, Any] | None = None
    results_summary: list[dict[str, Any]] | None = None
    report: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)


_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = asyncio.Lock()
_graph_app = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def get_graph_app():
    global _graph_app
    if _graph_app is None:
        settings = get_settings()
        setup_logging(settings.log_level)
        if settings.langsmith_tracing:
            os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
            if settings.langchain_api_key:
                os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)
            os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)
        _graph_app = build_graph(settings)
    return _graph_app


def create_app() -> FastAPI:
    app = FastAPI(
        title="Research Synthesis Agent",
        description="API para lanzar investigaciones multi-agente y obtener el informe.",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        settings = get_settings()
        return {
            "status": "ok",
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "search_provider": settings.search_provider,
            "papers_provider": settings.papers_provider,
        }

    @app.post("/api/research", response_model=JobCreateResponse)
    async def start_research(body: ResearchRequest) -> JobCreateResponse:
        query = body.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")

        job_id = uuid.uuid4().hex
        now = _now()
        job = {
            "job_id": job_id,
            "status": JobStatus.QUEUED,
            "query": query,
            "created_at": now,
            "updated_at": now,
            "stage": "En cola",
            "error": None,
            "plan": None,
            "results_summary": None,
            "report": None,
            "errors": [],
        }
        async with _jobs_lock:
            _jobs[job_id] = job

        asyncio.create_task(_run_job(job_id, query))
        return JobCreateResponse(job_id=job_id, status=JobStatus.QUEUED)

    @app.get("/api/research/{job_id}", response_model=JobResponse)
    async def get_research(job_id: str) -> JobResponse:
        async with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Job no encontrado.")
            return JobResponse(**job)

    if FRONTEND_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

    return app


async def _update_job(job_id: str, **fields: Any) -> None:
    async with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.update(fields)
        job["updated_at"] = _now()


async def _run_job(job_id: str, query: str) -> None:
    await _update_job(
        job_id,
        status=JobStatus.RUNNING,
        stage="Planificando investigación…",
    )
    try:
        app = get_graph_app()
        await _update_job(job_id, stage="Investigando fuentes en paralelo…")
        state = await app.arun(query)

        plan = state.get("plan")
        results = list(state.get("results") or [])
        report = state.get("report")
        errors = list(state.get("errors") or [])

        results_summary = [
            {
                "researcher_type": r.researcher_type.value
                if hasattr(r.researcher_type, "value")
                else str(r.researcher_type),
                "subquestion_id": r.subquestion_id,
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "findings_count": len(r.findings),
                "duration_ms": r.duration_ms,
                "error_message": r.error_message,
            }
            for r in results
        ]

        if report is None:
            await _update_job(
                job_id,
                status=JobStatus.FAILED,
                stage="Fallido",
                error="No se generó informe.",
                plan=plan.model_dump(mode="json") if plan else None,
                results_summary=results_summary,
                errors=errors,
            )
            return

        await _update_job(
            job_id,
            status=JobStatus.DONE,
            stage="Completado",
            plan=plan.model_dump(mode="json") if plan else None,
            results_summary=results_summary,
            report=report.model_dump(mode="json"),
            errors=errors,
            error=None,
        )
        logger.info(
            "Research job completed",
            extra={"agent": "api", "extra": {"job_id": job_id}},
        )
    except Exception as exc:  # noqa: BLE001 — surface to UI
        logger.exception(
            "Research job failed",
            extra={"agent": "api", "extra": {"job_id": job_id}},
        )
        await _update_job(
            job_id,
            status=JobStatus.FAILED,
            stage="Fallido",
            error=str(exc),
        )


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "src.api:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
