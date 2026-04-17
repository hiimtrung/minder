import uuid
import logging
from typing import Any, List

from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from minder.config import MinderConfig
from minder.observability.metrics import record_admin_operation
from minder.prompts.formatter import PromptDraft, polish_prompt_draft
from minder.prompts import PromptRegistry
from minder.store.interfaces import IOperationalStore
from .context import AdminRouteContext

logger = logging.getLogger(__name__)


class PromptCreateRequest(BaseModel):
    name: str
    title: str
    description: str
    content_template: str
    arguments: List[str] = Field(default_factory=list)


class PromptUpdateRequest(BaseModel):
    name: str | None = None
    title: str | None = None
    description: str | None = None
    content_template: str | None = None
    arguments: List[str] | None = None


class PromptPolishRequest(BaseModel):
    name: str
    title: str = ""
    description: str = ""
    content_template: str = ""
    arguments: List[str] = Field(default_factory=list)


def _serialize_prompt(prompt: Any) -> dict[str, Any]:
    return {
        "id": str(prompt.id),
        "name": prompt.name,
        "title": prompt.title,
        "description": prompt.description,
        "content_template": prompt.content_template,
        "arguments": list(getattr(prompt, "arguments", []) or []),
        "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
        "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
        "is_builtin": bool(getattr(prompt, "is_builtin", False)),
    }


async def _sync_prompts(context: AdminRouteContext) -> None:
    if context.prompt_sync_hook is None:
        return
    await context.prompt_sync_hook()


def _config_from_request(request: Request) -> MinderConfig:
    config = getattr(request.app.state, "config", None)
    if isinstance(config, MinderConfig):
        return config
    return MinderConfig()


def build_prompts_routes(context: AdminRouteContext) -> list[BaseRoute]:
    async def list_prompts(request: Request) -> JSONResponse:
        del request
        await record_admin_operation(
            operation="list_prompts",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            prompt_index = {
                prompt.name: prompt for prompt in PromptRegistry.builtin_prompt_models()
            }
            for prompt in await context.store.list_prompts():
                prompt_index[prompt.name] = prompt
            ordered_prompts = sorted(
                prompt_index.values(),
                key=lambda prompt: (
                    not bool(getattr(prompt, "is_builtin", False)),
                    prompt.name,
                ),
            )
            return JSONResponse(
                [_serialize_prompt(prompt) for prompt in ordered_prompts]
            )
        except Exception as e:
            logger.exception("Failed to list prompts", exc_info=e)
            return JSONResponse({"error": str(e)}, status_code=500)

    async def get_prompt(request: Request) -> JSONResponse:
        prompt_id = request.path_params["prompt_id"]
        await record_admin_operation(
            operation="get_prompt",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            prompt = await context.store.get_prompt_by_id(uuid.UUID(prompt_id))
            if not prompt:
                return JSONResponse({"error": "Prompt not found"}, status_code=404)
            return JSONResponse(_serialize_prompt(prompt))
        except Exception as e:
            logger.exception("Failed to get prompt", exc_info=e)
            return JSONResponse({"error": str(e)}, status_code=500)

    async def create_prompt(request: Request) -> JSONResponse:
        await record_admin_operation(
            operation="create_prompt",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            data = await request.json()
            payload = PromptCreateRequest(**data)
            prompt = await context.store.create_prompt(
                name=payload.name,
                title=payload.title,
                description=payload.description,
                content_template=payload.content_template,
                arguments=payload.arguments,
            )
            await _sync_prompts(context)
            return JSONResponse(_serialize_prompt(prompt), status_code=201)
        except Exception as e:
            logger.exception("Failed to create prompt", exc_info=e)
            return JSONResponse({"error": str(e)}, status_code=400)

    async def update_prompt(request: Request) -> JSONResponse:
        prompt_id = request.path_params["prompt_id"]
        await record_admin_operation(
            operation="update_prompt",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            data = await request.json()
            payload = PromptUpdateRequest(**data)
            update_data = payload.model_dump(exclude_unset=True)
            prompt = await context.store.update_prompt(
                uuid.UUID(prompt_id), **update_data
            )
            if not prompt:
                return JSONResponse({"error": "Prompt not found"}, status_code=404)
            await _sync_prompts(context)
            return JSONResponse(_serialize_prompt(prompt))
        except Exception as e:
            logger.exception("Failed to update prompt", exc_info=e)
            return JSONResponse({"error": str(e)}, status_code=400)

    async def delete_prompt(request: Request) -> JSONResponse:
        prompt_id = request.path_params["prompt_id"]
        await record_admin_operation(
            operation="delete_prompt",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            await context.store.delete_prompt(uuid.UUID(prompt_id))
            await _sync_prompts(context)
            return JSONResponse({"status": "deleted"}, status_code=200)
        except Exception as e:
            logger.exception("Failed to delete prompt", exc_info=e)
            return JSONResponse({"error": str(e)}, status_code=500)

    async def polish_prompt(request: Request) -> JSONResponse:
        await record_admin_operation(
            operation="polish_prompt",
            outcome="success",
            actor_id="system",
            store=context.store,
        )
        try:
            data = await request.json()
            payload = PromptPolishRequest(**data)
            polished, metadata = polish_prompt_draft(
                PromptDraft(
                    name=payload.name,
                    title=payload.title,
                    description=payload.description,
                    content_template=payload.content_template,
                    arguments=payload.arguments,
                ),
                _config_from_request(request),
            )
            return JSONResponse(
                {
                    "name": polished.name,
                    "title": polished.title,
                    "description": polished.description,
                    "content_template": polished.content_template,
                    "arguments": polished.arguments,
                    "llm": metadata,
                }
            )
        except Exception as e:
            logger.exception("Failed to polish prompt", exc_info=e)
            return JSONResponse({"error": str(e)}, status_code=400)

    return [
        Route("/api/v1/prompts", list_prompts, methods=["GET"]),
        Route("/api/v1/prompts", create_prompt, methods=["POST"]),
        Route("/api/v1/prompts/polish", polish_prompt, methods=["POST"]),
        Route("/api/v1/prompts/{prompt_id}", get_prompt, methods=["GET"]),
        Route("/api/v1/prompts/{prompt_id}", update_prompt, methods=["PATCH", "PUT"]),
        Route("/api/v1/prompts/{prompt_id}", delete_prompt, methods=["DELETE"]),
    ]
