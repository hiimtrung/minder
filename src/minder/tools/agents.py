from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from minder.store.interfaces import IOperationalStore


class AgentTools:
    def __init__(self, store: IOperationalStore) -> None:
        self._store = store

    async def minder_agent_list(
        self,
        *,
        workflow_step: str | None = None,
        tag: str | None = None,
        is_default: bool | None = None,
    ) -> list[dict[str, Any]]:
        """List subagent definitions. Omits system_prompt for context efficiency."""
        agents = await self._store.list_agents(
            workflow_step=workflow_step,
            tag=tag,
            is_default=is_default,
        )
        return [_serialize_agent_compact(a) for a in agents]

    async def minder_agent_get(self, name: str) -> dict[str, Any] | None:
        """Get full subagent definition by name, including system_prompt."""
        agent = await self._store.get_agent_by_name(name)
        if agent is None:
            return None
        return _serialize_agent_full(agent)

    async def minder_agent_store(
        self,
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
        """Create or update a subagent definition (upsert by name)."""
        agent = await self._store.upsert_agent(
            name,
            title=title,
            description=description,
            system_prompt=system_prompt,
            tools=tools or [],
            workflow_steps=workflow_steps or [],
            artifact_types=artifact_types or [],
            tags=tags or [],
            is_default=is_default,
        )
        return _serialize_agent_full(agent)

    async def minder_agent_update(
        self,
        name: str,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Partially update a subagent by name. Returns None if not found."""
        agent = await self._store.get_agent_by_name(name)
        if agent is None:
            return None
        kwargs["updated_at"] = datetime.now(UTC)
        updated = await self._store.update_agent(uuid.UUID(str(agent.id)), **kwargs)
        if updated is None:
            return None
        return _serialize_agent_full(updated)

    async def minder_agent_delete(self, name: str) -> dict[str, Any]:
        """Delete a subagent by name. Returns deletion status."""
        agent = await self._store.get_agent_by_name(name)
        if agent is None:
            return {"deleted": False, "name": name}
        await self._store.delete_agent(uuid.UUID(str(agent.id)))
        return {"deleted": True, "name": name}


def _serialize_agent_compact(agent: Any) -> dict[str, Any]:
    return {
        "id": str(agent.id),
        "name": str(agent.name),
        "title": str(agent.title),
        "description": str(agent.description),
        "tools": list(agent.tools or []),
        "workflow_steps": list(agent.workflow_steps or []),
        "artifact_types": list(agent.artifact_types or []),
        "tags": list(agent.tags or []),
        "is_default": bool(agent.is_default),
    }


def _serialize_agent_full(agent: Any) -> dict[str, Any]:
    return {
        **_serialize_agent_compact(agent),
        "system_prompt": str(agent.system_prompt),
    }
