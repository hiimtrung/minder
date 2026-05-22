"""
Agent Tool Handlers — MCP tool wrappers for SubAgent CRUD.

Extracted from bootstrap/transport.py to respect Single Responsibility.
"""

from __future__ import annotations

from typing import Any

from minder.tools.agents import AgentTools


def create_agent_handlers(agent_tools: AgentTools) -> dict[str, Any]:
    """Return a dict of {tool_name: handler_fn} for agent-related MCP tools."""

    async def minder_agent_list(
        *,
        user=None,  # noqa: ANN001
        workflow_step: str | None = None,
        tag: str | None = None,
        is_default: bool | None = None,
    ) -> list[dict[str, Any]]:
        del user
        return await agent_tools.minder_agent_list(
            workflow_step=workflow_step,
            tag=tag,
            is_default=is_default,
        )

    async def minder_agent_get(
        *,
        user=None,  # noqa: ANN001
        name: str,
    ) -> dict[str, Any] | None:
        del user
        return await agent_tools.minder_agent_get(name)

    async def minder_agent_store(
        *,
        user=None,  # noqa: ANN001
        name: str,
        title: str,
        description: str,
        system_prompt: str,
        tools: list[str] | None = None,
        workflow_steps: list[str] | None = None,
        artifact_types: list[str] | None = None,
        tags: list[str] | None = None,
        is_default: bool = False,
    ) -> dict[str, Any]:
        del user
        return await agent_tools.minder_agent_store(
            name,
            title=title,
            description=description,
            system_prompt=system_prompt,
            tools=tools,
            workflow_steps=workflow_steps,
            artifact_types=artifact_types,
            tags=tags,
            is_default=is_default,
        )

    async def minder_agent_update(
        *,
        user=None,  # noqa: ANN001
        name: str,
        title: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        tools: list[str] | None = None,
        workflow_steps: list[str] | None = None,
        artifact_types: list[str] | None = None,
        tags: list[str] | None = None,
        is_default: bool | None = None,
    ) -> dict[str, Any] | None:
        del user
        kwargs = {
            k: v
            for k, v in {
                "title": title,
                "description": description,
                "system_prompt": system_prompt,
                "tools": tools,
                "workflow_steps": workflow_steps,
                "artifact_types": artifact_types,
                "tags": tags,
                "is_default": is_default,
            }.items()
            if v is not None
        }
        return await agent_tools.minder_agent_update(name, **kwargs)

    async def minder_agent_delete(
        *,
        user=None,  # noqa: ANN001
        name: str,
    ) -> dict[str, Any]:
        del user
        return await agent_tools.minder_agent_delete(name)

    return {
        "minder_agent_list": minder_agent_list,
        "minder_agent_get": minder_agent_get,
        "minder_agent_store": minder_agent_store,
        "minder_agent_update": minder_agent_update,
        "minder_agent_delete": minder_agent_delete,
    }
