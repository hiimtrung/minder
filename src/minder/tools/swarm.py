"""Swarm MCP tools — thin wrappers over SwarmService for the blackboard substrate."""

from __future__ import annotations

from typing import Any

from minder.application.swarm.service import SwarmService


class SwarmTools:
    def __init__(self, service: SwarmService) -> None:
        self._service = service

    async def minder_swarm_create(self, *, goal: str, workflow_id: str | None = None) -> dict[str, Any]:
        return await self._service.create_swarm(goal=goal, workflow_id=workflow_id)

    async def minder_swarm_plan(self, *, swarm_id: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._service.plan(swarm_id=swarm_id, tasks=tasks)

    async def minder_swarm_propose(self, *, swarm_id: str) -> dict[str, Any]:
        return await self._service.propose(swarm_id=swarm_id)

    async def minder_swarm_approve(
        self,
        *,
        swarm_id: str,
        action: str,
        approved_by: str | None = None,
        workers: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return await self._service.approve(
            swarm_id=swarm_id, action=action, approved_by=approved_by, workers=workers
        )

    async def minder_swarm_join(
        self,
        *,
        swarm_id: str,
        runtime: str,
        role: str = "worker",
        workspace: str = "",
        session_id: str | None = None,
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._service.join(
            swarm_id=swarm_id,
            runtime=runtime,
            role=role,
            workspace=workspace,
            session_id=session_id,
            capabilities=capabilities,
        )

    async def minder_swarm_heartbeat(self, *, node_id: str, status: str | None = None) -> dict[str, Any]:
        return await self._service.heartbeat(node_id=node_id, status=status)

    async def minder_swarm_who(self, *, swarm_id: str) -> dict[str, Any]:
        return await self._service.who(swarm_id=swarm_id)

    async def minder_swarm_claim(self, *, task_id: str, node_id: str) -> dict[str, Any]:
        return await self._service.claim(task_id=task_id, node_id=node_id)

    async def minder_swarm_report(
        self,
        *,
        task_id: str,
        node_id: str,
        status: str = "done",
        result_ref: str | None = None,
        summary: str = "",
        artifact_refs: list[str] | None = None,
        facts: list[str] | None = None,
        to_task_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._service.report(
            task_id=task_id,
            node_id=node_id,
            status=status,
            result_ref=result_ref,
            summary=summary,
            artifact_refs=artifact_refs,
            facts=facts,
            to_task_id=to_task_id,
        )

    async def minder_swarm_block(self, *, task_id: str, reason: str) -> dict[str, Any]:
        return await self._service.block(task_id=task_id, reason=reason)

    async def minder_swarm_collect(self, *, swarm_id: str) -> dict[str, Any]:
        return await self._service.collect(swarm_id=swarm_id)
