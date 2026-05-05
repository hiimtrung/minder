from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from minder.tools.agents import AgentTools

from .context import AdminRouteContext

logger = logging.getLogger(__name__)


class AgentCreateRequest(BaseModel):
    name: str
    title: str
    description: str
    system_prompt: str
    tools: list[str] = Field(default_factory=list)
    workflow_steps: list[str] = Field(default_factory=list)
    artifact_types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    is_default: bool = False


class AgentUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    workflow_steps: list[str] | None = None
    artifact_types: list[str] | None = None
    tags: list[str] | None = None
    is_default: bool | None = None


def build_agents_routes(context: AdminRouteContext) -> list[BaseRoute]:
    agent_tools = AgentTools(context.store)

    async def list_agents(request: Request) -> JSONResponse:
        workflow_step = request.query_params.get("workflow_step")
        tag = request.query_params.get("tag")
        is_default_param = request.query_params.get("is_default")
        is_default: bool | None = None
        if is_default_param is not None:
            is_default = is_default_param.lower() in ("true", "1", "yes")

        agents = await agent_tools.minder_agent_list(
            workflow_step=workflow_step,
            tag=tag,
            is_default=is_default,
        )
        return JSONResponse(agents)

    async def get_agent(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        agent = await agent_tools.minder_agent_get(name)
        if agent is None:
            return JSONResponse(
                {"error": f"SubAgent '{name}' not found"}, status_code=404
            )
        return JSONResponse(agent)

    async def create_agent(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            payload = AgentCreateRequest(**body)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        agent = await agent_tools.minder_agent_store(
            payload.name,
            title=payload.title,
            description=payload.description,
            system_prompt=payload.system_prompt,
            tools=payload.tools,
            workflow_steps=payload.workflow_steps,
            artifact_types=payload.artifact_types,
            tags=payload.tags,
            is_default=payload.is_default,
        )
        return JSONResponse(agent, status_code=201)

    async def update_agent(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        try:
            body = await request.json()
            payload = AgentUpdateRequest(**body)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        kwargs = {k: v for k, v in payload.model_dump().items() if v is not None}
        updated = await agent_tools.minder_agent_update(name, **kwargs)
        if updated is None:
            return JSONResponse(
                {"error": f"SubAgent '{name}' not found"}, status_code=404
            )
        return JSONResponse(updated)

    async def delete_agent(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        result = await agent_tools.minder_agent_delete(name)
        return JSONResponse(result)

    return [
        Route("/api/v1/agents", list_agents, methods=["GET"]),
        Route("/api/v1/agents", create_agent, methods=["POST"]),
        Route("/api/v1/agents/{name}", get_agent, methods=["GET"]),
        Route("/api/v1/agents/{name}", update_agent, methods=["PATCH"]),
        Route("/api/v1/agents/{name}", delete_agent, methods=["DELETE"]),
    ]
