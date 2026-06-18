"""Swarm observability + control HTTP routes (CLI/OBS).

Read-only board/presence views plus the human approval action, backed by the
dedicated swarm store. Consumed by the dashboard ``swarm/`` page and the
``minder swarm`` CLI.
"""

from __future__ import annotations

import logging
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from minder.config import MinderConfig
from minder.domain.utils import _iso

from .context import AdminRouteContext

logger = logging.getLogger(__name__)


def build_swarm_routes(context: AdminRouteContext) -> list[BaseRoute]:
    store = context.swarm_store

    def _service():
        from minder.application.swarm.service import SwarmService

        config = getattr(context, "config", None) or MinderConfig()
        return SwarmService(store, config)

    async def list_swarms(_request: Request) -> JSONResponse:
        if store is None:
            return JSONResponse({"swarms": [], "enabled": False})
        swarms = await store.list_swarms()
        return JSONResponse(
            {
                "enabled": True,
                "swarms": [
                    {
                        "swarm_id": str(s.id),
                        "goal": s.goal,
                        "status": s.status,
                        "created_at": _iso(s.created_at) if s.created_at else None,
                        "finished_at": _iso(s.finished_at) if s.finished_at else None,
                    }
                    for s in swarms
                ],
            }
        )

    async def get_swarm(request: Request) -> JSONResponse:
        if store is None:
            return JSONResponse({"error": "swarm disabled"}, status_code=404)
        sid = uuid.UUID(request.path_params["swarm_id"])
        swarm = await store.get_swarm(sid)
        if swarm is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        nodes = await store.list_nodes(sid)
        tasks = await store.list_tasks(sid)
        handoffs = await store.list_handoffs(sid)
        manifest = await store.get_manifest_for_swarm(sid)
        return JSONResponse(
            {
                "swarm_id": str(swarm.id),
                "goal": swarm.goal,
                "status": swarm.status,
                "nodes": [
                    {
                        "node_id": str(n.id),
                        "runtime": n.runtime,
                        "role": n.role,
                        "status": n.status,
                        "workspace": n.workspace,
                        "current_task_id": str(n.current_task_id) if n.current_task_id else None,
                        "last_heartbeat_at": _iso(n.last_heartbeat_at) if n.last_heartbeat_at else None,
                    }
                    for n in nodes
                ],
                "tasks": [
                    {
                        "task_id": str(t.id),
                        "title": t.title,
                        "status": t.status,
                        "runtime_hint": t.runtime_hint,
                        "assignee_node_id": str(t.assignee_node_id) if t.assignee_node_id else None,
                        "depends_on": t.depends_on,
                        "attempts": t.attempts,
                        "block_reason": t.block_reason,
                        "result_ref": t.result_ref,
                    }
                    for t in tasks
                ],
                "manifest": None
                if manifest is None
                else {
                    "manifest_id": str(manifest.id),
                    "status": manifest.status,
                    "workers": manifest.workers,
                    "estimated_cost_note": manifest.estimated_cost_note,
                    "approved_by": manifest.approved_by,
                },
                "handoffs": [
                    {
                        "from_task_id": str(h.from_task_id) if h.from_task_id else None,
                        "summary": h.summary,
                        "artifact_refs": h.artifact_refs,
                        "facts": h.facts,
                    }
                    for h in handoffs
                ],
            }
        )

    async def approve_swarm(request: Request) -> JSONResponse:
        if store is None:
            return JSONResponse({"error": "swarm disabled"}, status_code=404)
        swarm_id = request.path_params["swarm_id"]
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        action = payload.get("action", "approve")
        workers = payload.get("workers")
        approved_by = payload.get("approved_by", "dashboard")
        try:
            result = await _service().approve(
                swarm_id=swarm_id, action=action, approved_by=approved_by, workers=workers
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"status": "success", **result})

    return [
        Route("/api/v1/swarms", list_swarms, methods=["GET"]),
        Route("/api/v1/swarms/{swarm_id}", get_swarm, methods=["GET"]),
        Route("/api/v1/swarms/{swarm_id}/approve", approve_swarm, methods=["POST"]),
    ]
