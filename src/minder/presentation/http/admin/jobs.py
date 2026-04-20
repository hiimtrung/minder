from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import BaseRoute, Route

from minder.application.admin.jobs import AdminJobService, iter_job_stream

from .context import AdminRouteContext

logger = logging.getLogger(__name__)


class AdminJobCreateRequest(BaseModel):
    job_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


def _job_service_from_request(
    request: Request,
    context: AdminRouteContext,
) -> AdminJobService:
    service = getattr(request.app.state, "job_service", None)
    if isinstance(service, AdminJobService):
        return service
    service = AdminJobService(context.store, context.config)
    request.app.state.job_service = service
    return service


def _serialize_job(job: Any) -> dict[str, Any]:
    created_at = getattr(job, "created_at", None)
    updated_at = getattr(job, "updated_at", None)
    started_at = getattr(job, "started_at", None)
    finished_at = getattr(job, "finished_at", None)
    progress_current = int(getattr(job, "progress_current", 0) or 0)
    progress_total = int(getattr(job, "progress_total", 0) or 0)
    progress_percent = 0
    if progress_total > 0:
        progress_percent = round((progress_current / progress_total) * 100, 1)
    return {
        "id": str(job.id),
        "job_type": str(getattr(job, "job_type", "")),
        "title": str(getattr(job, "title", "")),
        "status": str(getattr(job, "status", "queued")),
        "requested_by_user_id": (
            str(getattr(job, "requested_by_user_id", ""))
            if getattr(job, "requested_by_user_id", None)
            else None
        ),
        "payload": dict(getattr(job, "payload", {}) or {}),
        "result_payload": getattr(job, "result_payload", None),
        "error_message": getattr(job, "error_message", None),
        "progress_current": progress_current,
        "progress_total": progress_total,
        "progress_percent": progress_percent,
        "message": getattr(job, "message", None),
        "events": list(getattr(job, "events", []) or []),
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "started_at": started_at.isoformat() if started_at else None,
        "finished_at": finished_at.isoformat() if finished_at else None,
    }


def _job_title(job_type: str, payload: dict[str, Any]) -> str:
    if job_type == "skill_import_git":
        repo_url = str(payload.get("repo_url") or "").strip()
        return f"Import skills from {repo_url or 'Git repository'}"
    return job_type.replace("_", " ").strip() or "Admin job"


def build_jobs_routes(context: AdminRouteContext) -> list[BaseRoute]:
    async def create_job(request: Request) -> JSONResponse:
        try:
            admin_user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        try:
            payload = AdminJobCreateRequest(**(await request.json()))
            if payload.job_type != "skill_import_git":
                return JSONResponse(
                    {"error": f"Unsupported job type: {payload.job_type}"},
                    status_code=400,
                )
            service = _job_service_from_request(request, context)
            job = await service.enqueue(
                job_type=payload.job_type,
                title=_job_title(payload.job_type, payload.payload),
                requested_by_user_id=admin_user.id,
                payload=payload.payload,
            )
            return JSONResponse(_serialize_job(job), status_code=202)
        except Exception as exc:
            logger.exception("Failed to create admin job", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def list_jobs(request: Request) -> JSONResponse:
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        job_type = (request.query_params.get("job_type") or "").strip() or None
        status = (request.query_params.get("status") or "").strip() or None
        limit = int(request.query_params.get("limit") or 50)
        jobs = await context.store.list_admin_jobs(
            job_type=job_type,
            status=status,
            limit=limit,
        )
        return JSONResponse(
            {"jobs": [_serialize_job(job) for job in jobs], "limit": limit}
        )

    async def get_job(request: Request) -> JSONResponse:
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        job_id = uuid.UUID(str(request.path_params["job_id"]))
        job = await context.store.get_admin_job_by_id(job_id)
        if job is None:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        return JSONResponse(_serialize_job(job))

    async def stream_jobs(request: Request) -> StreamingResponse | JSONResponse:
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        job_type = (request.query_params.get("job_type") or "").strip() or None
        status_values = {
            value.strip()
            for value in (request.query_params.get("status") or "").split(",")
            if value.strip()
        }
        service = _job_service_from_request(request, context)
        queue, unsubscribe = service.subscribe(
            job_type=job_type,
            statuses=status_values or None,
        )

        async def event_stream():
            try:
                async for event in iter_job_stream(
                    queue=queue,
                    request_is_disconnected=request.is_disconnected,
                ):
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                unsubscribe()

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    async def stream_job(request: Request) -> StreamingResponse | JSONResponse:
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        job_id = uuid.UUID(str(request.path_params["job_id"]))
        existing = await context.store.get_admin_job_by_id(job_id)
        if existing is None:
            return JSONResponse({"error": "Job not found"}, status_code=404)

        service = _job_service_from_request(request, context)
        queue, unsubscribe = service.subscribe(job_id=str(job_id))

        async def event_stream():
            try:
                yield f"data: {json.dumps({'type': 'job', 'payload': _serialize_job(existing)})}\n\n"
                async for event in iter_job_stream(
                    queue=queue,
                    request_is_disconnected=request.is_disconnected,
                ):
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                unsubscribe()

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return [
        Route("/api/v1/jobs", list_jobs, methods=["GET"]),
        Route("/api/v1/jobs", create_job, methods=["POST"]),
        Route("/api/v1/jobs/stream", stream_jobs, methods=["GET"]),
        Route("/api/v1/jobs/{job_id}", get_job, methods=["GET"]),
        Route("/api/v1/jobs/{job_id}/stream", stream_job, methods=["GET"]),
    ]
