from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from minder.config import MinderConfig
from minder.embedding.local import LocalEmbeddingProvider
from minder.observability.metrics import record_admin_operation
from minder.tools.memory import MemoryTools

from .context import AdminRouteContext

logger = logging.getLogger(__name__)


class MemoryCreateRequest(BaseModel):
    title: str
    content: str
    language: str = "markdown"
    tags: list[str] = Field(default_factory=list)


class MemoryUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    language: str | None = None
    tags: list[str] | None = None


def _config_from_request(request: Request) -> MinderConfig:
    config = getattr(request.app.state, "config", None)
    if isinstance(config, MinderConfig):
        return config
    return MinderConfig()


def _serialize_memory(skill: Any) -> dict[str, Any]:
    return {
        "id": str(skill.id),
        "title": str(skill.title),
        "content": str(skill.content),
        "language": str(getattr(skill, "language", "markdown") or "markdown"),
        "tags": list(getattr(skill, "tags", []) or []),
        "created_at": skill.created_at.isoformat() if skill.created_at else None,
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
    }


def build_memories_routes(context: AdminRouteContext) -> list[BaseRoute]:
    async def list_memories(request: Request) -> JSONResponse:
        del request
        await record_admin_operation(
            operation="list_memories",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            skills = sorted(
                await context.store.list_skills(),
                key=lambda skill: (
                    str(getattr(skill, "title", "")).lower(),
                    str(getattr(skill, "language", "")).lower(),
                ),
            )
            return JSONResponse([_serialize_memory(skill) for skill in skills])
        except Exception as exc:
            logger.exception("Failed to list memories", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

    async def get_memory(request: Request) -> JSONResponse:
        memory_id = request.path_params["memory_id"]
        await record_admin_operation(
            operation="get_memory",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            skill = await context.store.get_skill_by_id(uuid.UUID(memory_id))
            if skill is None:
                return JSONResponse({"error": "Memory not found"}, status_code=404)
            return JSONResponse(_serialize_memory(skill))
        except Exception as exc:
            logger.exception("Failed to get memory", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

    async def create_memory(request: Request) -> JSONResponse:
        await record_admin_operation(
            operation="create_memory",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            payload = MemoryCreateRequest(**(await request.json()))
            tools = MemoryTools(context.store, _config_from_request(request))
            created = await tools.minder_memory_store(
                title=payload.title,
                content=payload.content,
                tags=payload.tags,
                language=payload.language,
            )
            skill = await context.store.get_skill_by_id(uuid.UUID(created["id"]))
            if skill is None:
                return JSONResponse(created, status_code=201)
            return JSONResponse(_serialize_memory(skill), status_code=201)
        except Exception as exc:
            logger.exception("Failed to create memory", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def update_memory(request: Request) -> JSONResponse:
        memory_id = request.path_params["memory_id"]
        await record_admin_operation(
            operation="update_memory",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            payload = MemoryUpdateRequest(**(await request.json()))
            existing = await context.store.get_skill_by_id(uuid.UUID(memory_id))
            if existing is None:
                return JSONResponse({"error": "Memory not found"}, status_code=404)

            update_data = payload.model_dump(exclude_unset=True)
            next_title = str(update_data.get("title") or existing.title)
            next_content = str(update_data.get("content") or existing.content)
            if "tags" in update_data and update_data["tags"] is not None:
                update_data["tags"] = [
                    str(tag).strip() for tag in update_data["tags"] if str(tag).strip()
                ]

            if "title" in update_data or "content" in update_data:
                config = _config_from_request(request)
                embedder = LocalEmbeddingProvider(
                    fastembed_model=config.embedding.fastembed_model,
                    fastembed_cache_dir=config.embedding.fastembed_cache_dir,
                    dimensions=min(config.embedding.dimensions, 16),
                    runtime="auto",
                )
                update_data["embedding"] = embedder.embed(
                    f"{next_title}\n{next_content}"
                )

            updated = await context.store.update_skill(
                uuid.UUID(memory_id), **update_data
            )
            if updated is None:
                return JSONResponse({"error": "Memory not found"}, status_code=404)
            return JSONResponse(_serialize_memory(updated))
        except Exception as exc:
            logger.exception("Failed to update memory", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def delete_memory(request: Request) -> JSONResponse:
        memory_id = request.path_params["memory_id"]
        await record_admin_operation(
            operation="delete_memory",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            skill = await context.store.get_skill_by_id(uuid.UUID(memory_id))
            if skill is None:
                return JSONResponse({"error": "Memory not found"}, status_code=404)
            await context.store.delete_skill(uuid.UUID(memory_id))
            return JSONResponse({"deleted": True}, status_code=200)
        except Exception as exc:
            logger.exception("Failed to delete memory", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

    return [
        Route("/api/v1/memories", list_memories, methods=["GET"]),
        Route("/api/v1/memories", create_memory, methods=["POST"]),
        Route("/api/v1/memories/{memory_id}", get_memory, methods=["GET"]),
        Route("/api/v1/memories/{memory_id}", update_memory, methods=["PATCH", "PUT"]),
        Route("/api/v1/memories/{memory_id}", delete_memory, methods=["DELETE"]),
    ]
