from __future__ import annotations

import uuid
from typing import Any

from minder.store.interfaces import IOperationalStore
from minder.store.repo_state import RepoStateStore


class WorkflowTools:
    def __init__(self, store: IOperationalStore, repo_state_store: RepoStateStore) -> None:
        self._store = store
        self._repo_state = repo_state_store

    async def minder_workflow_get(self, *, repo_id: uuid.UUID, repo_path: str) -> dict[str, Any]:
        repo = await self._require_repo(repo_id)
        workflow = await self._require_workflow(repo.workflow_id)
        state = await self._store.get_workflow_state_by_repo(repo_id)
        relationships = dict(repo.relationships) if isinstance(repo.relationships, dict) else {}
        await self._repo_state.write_relationships(repo_path, relationships)
        if state is not None:
            await self._repo_state.write_workflow_state(
                repo_path,
                {
                    "current_step": state.current_step,
                    "completed_steps": list(state.completed_steps),
                    "blocked_by": list(state.blocked_by),
                    "next_step": state.next_step,
                },
            )
        return {
            "workflow": {
                "id": str(workflow.id),
                "name": workflow.name,
                "steps": list(workflow.steps),
                "policies": dict(workflow.policies),
            }
        }

    async def minder_workflow_step(self, *, repo_id: uuid.UUID, repo_path: str) -> dict[str, Any]:
        state = await self._require_workflow_state(repo_id)
        payload = {
            "current_step": state.current_step,
            "completed_steps": list(state.completed_steps),
            "blocked_by": list(state.blocked_by),
            "next_step": state.next_step,
        }
        await self._repo_state.write_workflow_state(repo_path, payload)
        return payload

    async def minder_workflow_update(
        self,
        *,
        repo_id: uuid.UUID,
        repo_path: str,
        completed_step: str,
        artifact_name: str | None = None,
        artifact_content: str | None = None,
    ) -> dict[str, Any]:
        repo = await self._require_repo(repo_id)
        workflow = await self._require_workflow(repo.workflow_id)
        state = await self._require_workflow_state(repo_id)
        step_names = [step["name"] for step in workflow.steps if isinstance(step, dict) and "name" in step]
        completed_steps = list(state.completed_steps)
        if completed_step not in completed_steps:
            completed_steps.append(completed_step)
        next_step = self._next_step(completed_step, step_names)
        artifacts = dict(state.artifacts)
        if artifact_name and artifact_content is not None:
            artifacts[artifact_name] = artifact_content
            await self._repo_state.write_artifact(repo_path, artifact_name, artifact_content)
        updated = await self._store.update_workflow_state(
            state.id,
            completed_steps=completed_steps,
            current_step=next_step or completed_step,
            next_step=self._next_step(next_step or completed_step, step_names),
            artifacts=artifacts,
        )
        if updated is None:
            raise ValueError(f"Workflow state not found for repo: {repo_id}")
        await self._repo_state.write_workflow_state(
            repo_path,
            {
                "current_step": updated.current_step,
                "completed_steps": list(updated.completed_steps),
                "blocked_by": list(updated.blocked_by),
                "next_step": updated.next_step,
            },
        )
        await self._repo_state.write_relationships(
            repo_path,
            dict(repo.relationships) if isinstance(repo.relationships, dict) else {},
        )
        return {
            "current_step": updated.current_step,
            "completed_steps": list(updated.completed_steps),
            "next_step": updated.next_step,
            "artifacts": dict(updated.artifacts),
        }

    async def minder_workflow_guard(
        self,
        *,
        repo_id: uuid.UUID,
        requested_step: str,
    ) -> dict[str, Any]:
        repo = await self._require_repo(repo_id)
        workflow = await self._require_workflow(repo.workflow_id)
        state = await self._require_workflow_state(repo_id)
        step_names = [step["name"] for step in workflow.steps if isinstance(step, dict) and "name" in step]
        expected_next = self._next_step(state.current_step, step_names)
        allowed = requested_step == state.current_step or requested_step == expected_next and state.current_step in state.completed_steps
        reason = None if allowed else f"Requested step '{requested_step}' is not allowed from '{state.current_step}'"
        return {"allowed": allowed, "reason": reason, "expected_next": expected_next}

    async def _require_repo(self, repo_id: uuid.UUID):  # noqa: ANN202
        repo = await self._store.get_repository_by_id(repo_id)
        if repo is None:
            raise ValueError(f"Repository not found: {repo_id}")
        return repo

    async def _require_workflow(self, workflow_id: uuid.UUID | None):  # noqa: ANN202
        if workflow_id is None:
            raise ValueError("Repository has no workflow assigned")
        workflow = await self._store.get_workflow_by_id(workflow_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        return workflow

    async def _require_workflow_state(self, repo_id: uuid.UUID):  # noqa: ANN202
        state = await self._store.get_workflow_state_by_repo(repo_id)
        if state is None:
            raise ValueError(f"Workflow state not found for repo: {repo_id}")
        return state

    @staticmethod
    def _next_step(current_step: str, steps: list[str]) -> str | None:
        try:
            index = steps.index(current_step)
        except ValueError:
            return steps[0] if steps else None
        next_index = index + 1
        if next_index >= len(steps):
            return None
        return steps[next_index]
