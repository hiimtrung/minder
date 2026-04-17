from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from collections.abc import Awaitable

from minder.continuity import build_continuity_brief, build_instruction_envelope
from minder.graph.state import GraphState
from minder.store.interfaces import IGraphRepository, IOperationalStore

logger = logging.getLogger(__name__)


def _explicit_attribute(value: Any, name: str) -> Any | None:
    if value is None:
        return None
    if hasattr(value, "__dict__") and name in value.__dict__:
        return value.__dict__[name]
    return getattr(value, name, None)


class WorkflowPlannerNode:
    """Plan the workflow step and optionally enrich guidance with graph context.

    Args:
        store:       Operational store for workflow / session data.
        graph_store: Optional knowledge-graph store.  When provided the node
                     queries the graph for cross-service dependencies and
                     failing-test artefacts belonging to the current repo and
                     appends that context to the ``guidance`` string.
                     Omitting it (or passing ``None``) restores the original
                     behaviour and is fully backwards-compatible.
    """

    def __init__(
        self,
        store: IOperationalStore,
        *,
        graph_store: IGraphRepository | None = None,
    ) -> None:
        self._store = store
        self._graph_store = graph_store

    async def _load_session(self, session_id: Any) -> Any:
        result = self._store.get_session_by_id(session_id)
        if isinstance(result, Awaitable):
            return await result
        return result

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
            raw_steps: list[Any] = (
                workflow.steps if isinstance(workflow.steps, list) else []
            )
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
        instruction_envelope: dict[str, Any] | None = None
        continuity_brief: dict[str, Any] | None = None
        session = None
        workflow_state_session_id = _explicit_attribute(workflow_state, "session_id")
        if state.session_id is not None:
            session = await self._load_session(state.session_id)
        elif workflow_state_session_id is not None:
            session = await self._load_session(workflow_state_session_id)

        if workflow is not None and workflow_state is not None:
            instruction_envelope = build_instruction_envelope(
                workflow=workflow,
                workflow_state=workflow_state,
            )
            if session is not None:
                continuity_brief = build_continuity_brief(
                    session=session,
                    workflow_state=workflow_state,
                    workflow=workflow,
                )
            guidance = self._format_guidance(
                guidance,
                instruction_envelope=instruction_envelope,
                continuity_brief=continuity_brief,
            )

        # ------------------------------------------------------------------
        # Graph-enriched guidance (P3-T12)
        # ------------------------------------------------------------------
        if self._graph_store is not None and state.repo_path:
            graph_guidance = await self._build_graph_guidance(
                state.repo_path, artifacts
            )
            if graph_guidance:
                guidance = guidance + "\n\n" + graph_guidance

        cross_repo_context = str(
            state.workflow_context.get("cross_repo_context", "") or ""
        ).strip()
        if cross_repo_context:
            guidance = guidance + "\n\n" + cross_repo_context

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
                "instruction_envelope": instruction_envelope or {},
                "continuity_brief": continuity_brief or {},
            }
        )
        return state

    # ------------------------------------------------------------------
    # Graph guidance helper
    # ------------------------------------------------------------------

    async def _build_graph_guidance(
        self, repo_path: str, artifacts: dict[str, Any]
    ) -> str:
        """Query the graph store for dependency context for *repo_path*.

        Returns a non-empty string with additional guidance lines, or an
        empty string when no relevant graph data is found.  All exceptions
        from the graph store are caught and logged so that a graph query
        failure never breaks the workflow pipeline.
        """
        repo_name = Path(repo_path).name
        lines: list[str] = []

        try:
            service_nodes = await self._graph_store.query_by_type("service")  # type: ignore[union-attr]
        except Exception as exc:  # pragma: no cover
            logger.debug("graph_store.query_by_type failed: %s", exc)
            return ""

        # Find the service node that best matches this repo path.
        matching = [
            n
            for n in service_nodes
            if n.name == repo_name
            or (
                hasattr(n, "node_metadata")
                and n.node_metadata.get("path", "").startswith(repo_path)
            )
        ]

        if not matching:
            return ""

        service = matching[0]

        # Cross-service dependencies via ``depends_on`` edges.
        try:
            dep_neighbors = await self._graph_store.get_neighbors(  # type: ignore[union-attr]
                service.id,
                direction="out",
                relation="depends_on",
            )
        except Exception as exc:  # pragma: no cover
            logger.debug("graph_store.get_neighbors failed: %s", exc)
            dep_neighbors = []

        if dep_neighbors:
            dep_names = sorted({n.name for n in dep_neighbors})
            lines.append(
                f"Cross-service dependencies detected: {', '.join(dep_names)}. "
                "Ensure changes do not break these dependency contracts."
            )

        # Failing tests recorded in the last workflow artefact run.
        failing = artifacts.get("failing_tests")
        if failing:
            lines.append(f"Failing tests from last run: {failing}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

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
            return (
                "Current step: Review. Focus on correctness, regressions, and coverage."
            )
        return f"Current step: {current_step}. Follow the workflow and do not skip prerequisites."

    @staticmethod
    def _format_guidance(
        base_guidance: str,
        *,
        instruction_envelope: dict[str, Any],
        continuity_brief: dict[str, Any] | None,
    ) -> str:
        sections = [base_guidance]
        sections.append(f"Instruction envelope: {instruction_envelope}")
        if continuity_brief:
            sections.append(f"Continuity brief: {continuity_brief}")
        return "\n\n".join(sections)
