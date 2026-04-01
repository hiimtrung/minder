from __future__ import annotations

from typing import Any

from minder.graph.state import GraphState
from minder.store.relational import RelationalStore


class WorkflowPlannerNode:
    def __init__(self, store: RelationalStore) -> None:
        self._store = store

    async def run(self, state: GraphState) -> GraphState:
        workflow = None
        if state.workflow_context.get("workflow_name"):
            workflow = await self._store.get_workflow_by_name(
                state.workflow_context["workflow_name"]
            )

        if workflow is None:
            workflows = await self._store.list_workflows()
            workflow = next((item for item in workflows if item.default_for_repo), None)
            if workflow is None and workflows:
                workflow = workflows[0]

        workflow_steps: list[dict[str, Any]] = []
        if workflow is not None:
            raw_steps: list[Any] = workflow.steps if isinstance(workflow.steps, list) else []
            workflow_steps = [step for step in raw_steps if isinstance(step, dict)]

        workflow_state = None
        if state.repo_id is not None:
            workflow_state = await self._store.get_workflow_state_by_repo(state.repo_id)

        if not workflow_steps:
            workflow_steps = [{"name": "Test Writing"}, {"name": "Implementation"}]

        current_step = workflow_steps[0]["name"]
        completed_steps: list[str] = []
        blocked_by: list[str] = []
        artifacts: dict[str, Any] = {}
        if workflow_state is not None:
            current_step = workflow_state.current_step
            completed_steps = list(workflow_state.completed_steps)
            blocked_by = list(workflow_state.blocked_by)
            artifacts = dict(workflow_state.artifacts)

        next_step = self._next_step(current_step, workflow_steps)
        guidance = self._guidance_for_step(current_step)

        state.workflow_context.update(
            {
                "workflow_name": workflow.name if workflow is not None else "default",
                "workflow_steps": workflow_steps,
                "current_step": current_step,
                "next_step": next_step,
                "completed_steps": completed_steps,
                "blocked_by": blocked_by,
                "artifacts": artifacts,
                "guidance": guidance,
            }
        )
        return state

    @staticmethod
    def _next_step(current_step: str, steps: list[dict[str, Any]]) -> str | None:
        names = [step["name"] for step in steps]
        if current_step not in names:
            return names[0] if names else None
        current_index = names.index(current_step)
        if current_index + 1 >= len(names):
            return None
        return names[current_index + 1]

    @staticmethod
    def _guidance_for_step(current_step: str) -> str:
        lowered = current_step.lower()
        if "test" in lowered:
            return "Current step: Test Writing. Write tests before implementation."
        if "implement" in lowered:
            return "Current step: Implementation. Use existing failing tests as the contract."
        if "review" in lowered:
            return "Current step: Review. Focus on correctness, regressions, and coverage."
        return f"Current step: {current_step}. Follow the workflow and do not skip prerequisites."
