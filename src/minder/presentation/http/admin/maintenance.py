from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from minder.config import MinderConfig
from minder.application.maintenance.scheduler import get_scheduler
from minder.domain.utils import _iso

from .context import AdminRouteContext

logger = logging.getLogger(__name__)


class JobConfigUpdateRequest(BaseModel):
    schedule: str | None = None
    enabled: bool | None = None
    require_idle: bool | None = None
    max_runtime_s: int | None = None


class MaintenanceConfigUpdateRequest(BaseModel):
    mode: str | None = None
    enabled: bool | None = None
    idle_threshold_seconds: int | None = None
    auto_active_after_idle_hours: float | None = None


def build_maintenance_routes(context: AdminRouteContext) -> list[BaseRoute]:
    async def get_status(request: Request) -> JSONResponse:
        scheduler = get_scheduler()
        config = getattr(request.app.state, "config", None) or MinderConfig()
        
        jobs = await context.store.list_maintenance_jobs()
        serialized_jobs = []
        for job in jobs:
            serialized_jobs.append({
                "id": str(job.id),
                "name": job.name,
                "schedule": job.schedule,
                "enabled": job.enabled,
                "require_idle": job.require_idle,
                "max_runtime_s": job.max_runtime_s,
                "last_run_at": _iso(job.last_run_at) if job.last_run_at else None,
                "last_status": job.last_status,
                "last_summary": job.last_summary,
            })
            
        status = {
            "enabled": config.maintenance.enabled if scheduler is None else scheduler._config.maintenance.enabled,
            "mode": config.maintenance.mode if scheduler is None else scheduler.current_mode,
            "configured_mode": config.maintenance.mode if scheduler is None else scheduler._config.maintenance.mode,
            "idle_threshold_seconds": config.maintenance.idle_threshold_seconds if scheduler is None else scheduler._config.maintenance.idle_threshold_seconds,
            "auto_active_after_idle_hours": config.maintenance.auto_active_after_idle_hours if scheduler is None else scheduler._config.maintenance.auto_active_after_idle_hours,
            "is_idle": False if scheduler is None else scheduler.is_idle,
            "last_activity_time": _iso(scheduler._last_activity_time) if scheduler else None,
            "active_session_count": len(scheduler._active_sessions) if scheduler else 0,
            "jobs": serialized_jobs,
        }
        return JSONResponse(status)

    async def get_runs(request: Request) -> JSONResponse:
        params = request.query_params
        limit = int(params.get("limit", 50))
        offset = int(params.get("offset", 0))
        
        runs = await context.store.list_maintenance_runs(limit=limit, offset=offset)
        serialized_runs = []
        for run in runs:
            serialized_runs.append({
                "id": str(run.id),
                "job_name": run.job_name,
                "started_at": _iso(run.started_at),
                "finished_at": _iso(run.finished_at) if run.finished_at else None,
                "status": run.status,
                "duration_s": run.duration_s,
                "mode": run.mode,
                "summary": run.summary,
                "error_message": run.error_message,
            })
        return JSONResponse(serialized_runs)

    async def trigger_job(request: Request) -> JSONResponse:
        job_name = request.path_params["job_name"]
        scheduler = get_scheduler()
        if scheduler is None:
            return JSONResponse({"error": "Scheduler is not running"}, status_code=500)
            
        job = await context.store.get_maintenance_job_by_name(job_name)
        if not job:
            return JSONResponse({"error": f"Job not found: {job_name}"}, status_code=404)
            
        asyncio.create_task(scheduler.run_job(job))
        return JSONResponse({"status": "triggered", "message": f"Job '{job_name}' has been triggered."})

    async def update_job_config(request: Request) -> JSONResponse:
        job_name = request.path_params["job_name"]
        try:
            payload = JobConfigUpdateRequest(**(await request.json()))
        except Exception as e:
            return JSONResponse({"error": f"Invalid payload: {e}"}, status_code=400)
            
        job = await context.store.get_maintenance_job_by_name(job_name)
        if not job:
            return JSONResponse({"error": f"Job not found: {job_name}"}, status_code=404)
            
        if payload.schedule is not None:
            from croniter import croniter  # type: ignore[import-untyped]
            try:
                croniter(payload.schedule)
            except Exception as e:
                return JSONResponse({"error": f"Invalid cron expression: {e}"}, status_code=400)
                
        kwargs: dict[str, Any] = {}
        if payload.schedule is not None:
            kwargs["schedule"] = payload.schedule
        if payload.enabled is not None:
            kwargs["enabled"] = payload.enabled
        if payload.require_idle is not None:
            kwargs["require_idle"] = payload.require_idle
        if payload.max_runtime_s is not None:
            kwargs["max_runtime_s"] = payload.max_runtime_s
            
        updated = await context.store.update_maintenance_job(job.id, **kwargs)
        if updated is None:
            return JSONResponse({"error": "Failed to update job"}, status_code=500)

        scheduler = get_scheduler()
        if scheduler:
            for j_cfg in scheduler._config.maintenance.jobs:
                if j_cfg.name == job_name:
                    if payload.schedule is not None:
                        j_cfg.schedule = payload.schedule
                    if payload.require_idle is not None:
                        j_cfg.require_idle = payload.require_idle
                    if payload.max_runtime_s is not None:
                        j_cfg.max_runtime_s = payload.max_runtime_s
                        
        return JSONResponse({
            "status": "success",
            "job": {
                "name": updated.name,
                "schedule": updated.schedule,
                "enabled": updated.enabled,
                "require_idle": updated.require_idle,
                "max_runtime_s": updated.max_runtime_s,
            }
        })

    async def update_global_config(request: Request) -> JSONResponse:
        try:
            payload = MaintenanceConfigUpdateRequest(**(await request.json()))
        except Exception as e:
            return JSONResponse({"error": f"Invalid payload: {e}"}, status_code=400)
            
        scheduler = get_scheduler()
        config = getattr(request.app.state, "config", None) or MinderConfig()
        
        if payload.mode is not None:
            if payload.mode not in {"report", "active"}:
                return JSONResponse({"error": "Mode must be 'report' or 'active'"}, status_code=400)
            config.maintenance.mode = payload.mode
        if payload.enabled is not None:
            config.maintenance.enabled = payload.enabled
        if payload.idle_threshold_seconds is not None:
            config.maintenance.idle_threshold_seconds = payload.idle_threshold_seconds
        if payload.auto_active_after_idle_hours is not None:
            config.maintenance.auto_active_after_idle_hours = payload.auto_active_after_idle_hours
            
        if scheduler:
            scheduler._config.maintenance.mode = config.maintenance.mode
            scheduler._config.maintenance.enabled = config.maintenance.enabled
            scheduler._config.maintenance.idle_threshold_seconds = config.maintenance.idle_threshold_seconds
            scheduler._config.maintenance.auto_active_after_idle_hours = config.maintenance.auto_active_after_idle_hours
            
        return JSONResponse({
            "status": "success",
            "config": {
                "enabled": config.maintenance.enabled,
                "mode": config.maintenance.mode,
                "idle_threshold_seconds": config.maintenance.idle_threshold_seconds,
                "auto_active_after_idle_hours": config.maintenance.auto_active_after_idle_hours,
            }
        })

    return [
        Route("/api/v1/maintenance/status", get_status, methods=["GET"]),
        Route("/api/v1/maintenance/runs", get_runs, methods=["GET"]),
        Route("/api/v1/maintenance/jobs/{job_name}/trigger", trigger_job, methods=["POST"]),
        Route("/api/v1/maintenance/jobs/{job_name}/config", update_job_config, methods=["PUT"]),
        Route("/api/v1/maintenance/config", update_global_config, methods=["PUT"]),
    ]
