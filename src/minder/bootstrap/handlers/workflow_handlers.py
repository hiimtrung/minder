"""
Workflow Tool Handlers — MCP tool wrappers for workflow operations.

Extracted from bootstrap/transport.py to respect Single Responsibility.
"""

from __future__ import annotations

import uuid
from typing import Any

from minder.bootstrap.handlers.authorization import resolve_repo_uuid
from minder.domain.interfaces.repositories import IOperationalStore
from minder.tools.workflow import WorkflowTools


def create_workflow_handlers(
    workflow_tools: WorkflowTools,
    store: IOperationalStore,
) -> dict[str, Any]:
    """Return a dict of {tool_name: handler_fn} for workflow-related MCP tools."""

    async def minder_workflow_step(
        *,
        user=None,
        repo_id: str | None = None,
        repo_path: str | None = None,
        session_id: str | None = None,
        decision: dict[str, Any] | None = None,
        branch: str = "main",
        include_definition: bool = False,
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_step(
            repo_id=await resolve_repo_uuid(repo_id, store) if repo_id else None,
            repo_path=repo_path,
            session_id=uuid.UUID(session_id) if session_id else None,
            decision=decision,
            branch=branch,
            include_definition=include_definition,
        )

    async def minder_workflow_update(
        *,
        user=None,
        repo_id: str,
        repo_path: str,
        completed_step: str,
        artifact_name: str | None = None,
        artifact_content: str | None = None,
        branch: str = "main",
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_update(
            repo_id=await resolve_repo_uuid(repo_id, store),
            repo_path=repo_path,
            completed_step=completed_step,
            artifact_name=artifact_name,
            artifact_content=artifact_content,
            branch=branch,
        )

    async def minder_workflow_guard(
        *, user=None, repo_id: str, requested_step: str, action: str | None = None, branch: str = "main"
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_guard(
            repo_id=await resolve_repo_uuid(repo_id, store),
            requested_step=requested_step,
            action=action,
            branch=branch,
        )

    return {
        "minder_workflow_step": minder_workflow_step,
        "minder_workflow_update": minder_workflow_update,
        "minder_workflow_guard": minder_workflow_guard,
    }
