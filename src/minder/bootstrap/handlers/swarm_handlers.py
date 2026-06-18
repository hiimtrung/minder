"""Swarm Tool Handlers — MCP wrappers for the coordination substrate."""

from __future__ import annotations

from typing import Any

from minder.tools.swarm import SwarmTools


def create_swarm_handlers(swarm_tools: SwarmTools) -> dict[str, Any]:
    """Return {tool_name: handler_fn} for swarm coordination MCP tools."""

    async def minder_swarm_create(*, user=None, goal: str, workflow_id: str | None = None):  # noqa: ANN001
        del user
        return await swarm_tools.minder_swarm_create(goal=goal, workflow_id=workflow_id)

    async def minder_swarm_plan(*, user=None, swarm_id: str, tasks: list[dict[str, Any]]):  # noqa: ANN001
        del user
        return await swarm_tools.minder_swarm_plan(swarm_id=swarm_id, tasks=tasks)

    async def minder_swarm_propose(*, user=None, swarm_id: str):  # noqa: ANN001
        del user
        return await swarm_tools.minder_swarm_propose(swarm_id=swarm_id)

    async def minder_swarm_approve(  # noqa: ANN001
        *,
        user=None,
        swarm_id: str,
        action: str,
        approved_by: str | None = None,
        workers: list[dict[str, Any]] | None = None,
    ):
        del user
        return await swarm_tools.minder_swarm_approve(
            swarm_id=swarm_id, action=action, approved_by=approved_by, workers=workers
        )

    async def minder_swarm_join(  # noqa: ANN001
        *,
        user=None,
        swarm_id: str,
        runtime: str,
        role: str = "worker",
        workspace: str = "",
        session_id: str | None = None,
        capabilities: list[str] | None = None,
    ):
        del user
        return await swarm_tools.minder_swarm_join(
            swarm_id=swarm_id,
            runtime=runtime,
            role=role,
            workspace=workspace,
            session_id=session_id,
            capabilities=capabilities,
        )

    async def minder_swarm_heartbeat(*, user=None, node_id: str, status: str | None = None):  # noqa: ANN001
        del user
        return await swarm_tools.minder_swarm_heartbeat(node_id=node_id, status=status)

    async def minder_swarm_who(*, user=None, swarm_id: str):  # noqa: ANN001
        del user
        return await swarm_tools.minder_swarm_who(swarm_id=swarm_id)

    async def minder_swarm_claim(*, user=None, task_id: str, node_id: str):  # noqa: ANN001
        del user
        return await swarm_tools.minder_swarm_claim(task_id=task_id, node_id=node_id)

    async def minder_swarm_report(  # noqa: ANN001
        *,
        user=None,
        task_id: str,
        node_id: str,
        status: str = "done",
        result_ref: str | None = None,
        summary: str = "",
        artifact_refs: list[str] | None = None,
        facts: list[str] | None = None,
        to_task_id: str | None = None,
    ):
        del user
        return await swarm_tools.minder_swarm_report(
            task_id=task_id,
            node_id=node_id,
            status=status,
            result_ref=result_ref,
            summary=summary,
            artifact_refs=artifact_refs,
            facts=facts,
            to_task_id=to_task_id,
        )

    async def minder_swarm_block(*, user=None, task_id: str, reason: str):  # noqa: ANN001
        del user
        return await swarm_tools.minder_swarm_block(task_id=task_id, reason=reason)

    async def minder_swarm_collect(*, user=None, swarm_id: str):  # noqa: ANN001
        del user
        return await swarm_tools.minder_swarm_collect(swarm_id=swarm_id)

    return {
        "minder_swarm_create": minder_swarm_create,
        "minder_swarm_plan": minder_swarm_plan,
        "minder_swarm_propose": minder_swarm_propose,
        "minder_swarm_approve": minder_swarm_approve,
        "minder_swarm_join": minder_swarm_join,
        "minder_swarm_heartbeat": minder_swarm_heartbeat,
        "minder_swarm_who": minder_swarm_who,
        "minder_swarm_claim": minder_swarm_claim,
        "minder_swarm_report": minder_swarm_report,
        "minder_swarm_block": minder_swarm_block,
        "minder_swarm_collect": minder_swarm_collect,
    }
