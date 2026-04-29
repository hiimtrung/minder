from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from minder.config import MinderConfig
from minder.observability.metrics import record_admin_operation
from minder.tools.memory import is_memory_record
from minder.tools.skills import SkillTools

from .context import AdminRouteContext

logger = logging.getLogger(__name__)


class SkillCreateRequest(BaseModel):
    title: str
    content: str
    language: str
    tags: list[str] = Field(default_factory=list)
    workflow_steps: list[str] = Field(default_factory=list)
    artifact_types: list[str] = Field(default_factory=list)
    provenance: str | None = None
    quality_score: float = 0.0
    source: dict[str, Any] | None = None
    excerpt_kind: str = "none"


class SkillUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    language: str | None = None
    tags: list[str] | None = None
    workflow_steps: list[str] | None = None
    artifact_types: list[str] | None = None
    provenance: str | None = None
    quality_score: float | None = None
    deprecated: bool | None = None
    source: dict[str, Any] | None = None
    excerpt_kind: str | None = None


class SkillImportRequest(BaseModel):
    repo_url: str
    path: str = "skills"
    ref: str | None = None
    provider: str | None = None
    excerpt_kind: str = "none"


def _config_from_request(request: Request) -> MinderConfig:
    config = getattr(request.app.state, "config", None)
    if isinstance(config, MinderConfig):
        return config
    return MinderConfig()


def _artifact_tags() -> set[str]:
    return set(SkillTools._ARTIFACT_TAGS)


def _serialize_skill(skill: Any) -> dict[str, Any]:
    tags = list(getattr(skill, "tags", []) or [])
    artifact_tags = _artifact_tags()
    source_metadata = getattr(skill, "source_metadata", None)
    return {
        "id": str(skill.id),
        "title": str(skill.title),
        "content": str(skill.content),
        "language": str(getattr(skill, "language", "")),
        "tags": tags,
        "quality_score": round(float(getattr(skill, "quality_score", 0.0) or 0.0), 4),
        "usage_count": int(getattr(skill, "usage_count", 0) or 0),
        "workflow_step_tags": [
            tag for tag in tags if ":" not in tag and tag not in artifact_tags
        ],
        "artifact_type_tags": [tag for tag in tags if tag in artifact_tags],
        "provenance": next(
            (tag.split(":", 1)[1] for tag in tags if tag.startswith("source:")),
            None,
        ),
        "source": dict(source_metadata) if isinstance(source_metadata, dict) else None,
        "excerpt_kind": str(getattr(skill, "excerpt_kind", "none") or "none"),
        "created_at": skill.created_at.isoformat() if skill.created_at else None,
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
    }


def build_skills_routes(context: AdminRouteContext) -> list[BaseRoute]:
    async def list_skills(request: Request) -> JSONResponse:
        del request
        await record_admin_operation(
            operation="list_skills",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            all_skills = await context.store.list_skills()
            skills = sorted(
                [
                    s
                    for s in all_skills
                    if not is_memory_record(s)
                ],
                key=lambda skill: (
                    -float(getattr(skill, "quality_score", 0.0) or 0.0),
                    str(getattr(skill, "title", "")).lower(),
                ),
            )
            return JSONResponse([_serialize_skill(skill) for skill in skills])
        except Exception as exc:
            logger.exception("Failed to list skills", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

    async def get_skill(request: Request) -> JSONResponse:
        skill_id = request.path_params["skill_id"]
        await record_admin_operation(
            operation="get_skill",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            skill = await context.store.get_skill_by_id(uuid.UUID(skill_id))
            if not skill:
                return JSONResponse({"error": "Skill not found"}, status_code=404)
            return JSONResponse(_serialize_skill(skill))
        except Exception as exc:
            logger.exception("Failed to get skill", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

    async def create_skill(request: Request) -> JSONResponse:
        await record_admin_operation(
            operation="create_skill",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            payload = SkillCreateRequest(**(await request.json()))
            tools = SkillTools(context.store, _config_from_request(request))
            skill = await tools.minder_skill_store(
                title=payload.title,
                content=payload.content,
                language=payload.language,
                tags=payload.tags,
                workflow_steps=payload.workflow_steps,
                artifact_types=payload.artifact_types,
                provenance=payload.provenance,
                quality_score=payload.quality_score,
                source_metadata=payload.source,
                excerpt_kind=payload.excerpt_kind,
            )
            return JSONResponse(skill, status_code=201)
        except Exception as exc:
            logger.exception("Failed to create skill", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def update_skill(request: Request) -> JSONResponse:
        skill_id = request.path_params["skill_id"]
        await record_admin_operation(
            operation="update_skill",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            payload = SkillUpdateRequest(**(await request.json()))
            tools = SkillTools(context.store, _config_from_request(request))
            update_data = payload.model_dump(exclude={"source"}, exclude_unset=True)
            skill = await tools.minder_skill_update(
                skill_id,
                **update_data,
                source_metadata=payload.source,
            )
            return JSONResponse(skill)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        except Exception as exc:
            logger.exception("Failed to update skill", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def import_skills(request: Request) -> JSONResponse:
        await record_admin_operation(
            operation="import_skills",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            payload = SkillImportRequest(**(await request.json()))
            tools = SkillTools(context.store, _config_from_request(request))
            summary = await tools.minder_skill_import_git(
                repo_url=payload.repo_url,
                source_path=payload.path,
                ref=payload.ref,
                provider=payload.provider,
                excerpt_kind=payload.excerpt_kind,
            )
            return JSONResponse(summary, status_code=201)
        except Exception as exc:
            logger.exception("Failed to import skills", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def delete_skill(request: Request) -> JSONResponse:
        skill_id = request.path_params["skill_id"]
        await record_admin_operation(
            operation="delete_skill",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            skill = await context.store.get_skill_by_id(uuid.UUID(skill_id))
            if skill is None:
                return JSONResponse({"error": "Skill not found"}, status_code=404)
            await context.store.delete_skill(uuid.UUID(skill_id))
            return JSONResponse({"status": "deleted"}, status_code=200)
        except Exception as exc:
            logger.exception("Failed to delete skill", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

    return [
        Route("/api/v1/skills", list_skills, methods=["GET"]),
        Route("/api/v1/skills", create_skill, methods=["POST"]),
        Route("/api/v1/skills/imports", import_skills, methods=["POST"]),
        Route("/api/v1/skills/{skill_id}", get_skill, methods=["GET"]),
        Route("/api/v1/skills/{skill_id}", update_skill, methods=["PATCH", "PUT"]),
        Route("/api/v1/skills/{skill_id}", delete_skill, methods=["DELETE"]),
    ]
