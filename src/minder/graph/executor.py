from __future__ import annotations

from dataclasses import dataclass, field

from minder.graph.edges import determine_next_edge
from minder.graph.nodes import (
    ClarificationNode,
    EvaluatorNode,
    GuardNode,
    LLMNode,
    PlanningNode,
    ReasoningNode,
    RerankerNode,
    ReflectionNode,
    RetrieverNode,
    VerificationNode,
    WorkflowPlannerNode,
)
from minder.graph.runtime import graph_runtime_name, load_langgraph_state_graph
from minder.graph.state import GraphState


@dataclass
class GraphNodes:
    workflow_planner: WorkflowPlannerNode
    planning: PlanningNode
    clarification: ClarificationNode
    retriever: RetrieverNode
    reasoning: ReasoningNode
    llm: LLMNode
    guard: GuardNode
    verification: VerificationNode
    evaluator: EvaluatorNode
    reranker: RerankerNode | None = field(default=None)
    reflection: ReflectionNode | None = field(default=None)


class InternalGraphExecutor:
    def __init__(self, nodes: GraphNodes) -> None:
        self._nodes = nodes

    async def run(self, state: GraphState) -> GraphState:
        max_attempts = int(state.metadata.get("max_attempts", 1))
        state.metadata.setdefault("attempt_failures", [])
        state.metadata["orchestration_runtime"] = "internal"
        state = await self._nodes.workflow_planner.run(state)
        state = self._nodes.planning.run(state)
        state = self._nodes.clarification.run(state)
        if state.metadata.get("needs_clarification"):
            return state
        state = await self._nodes.retriever.run(state)
        if self._nodes.reranker is not None:
            state = await self._nodes.reranker.run(state)

        attempt = 0
        while True:
            attempt += 1
            state.retry_count = attempt - 1
            state = self._nodes.reasoning.run(state)
            state = self._nodes.llm.run(state)
            state = self._nodes.guard.run(state)
            state = self._nodes.verification.run(state)
            edge = determine_next_edge(state)
            state.transition_log.append(
                {
                    "attempt": attempt,
                    "edge": edge,
                    "provider": state.llm_output.get("provider"),
                    "fallback_used": state.metadata.get("fallback_used", False),
                }
            )
            if (
                edge not in {"verification_failed", "guard_failed"}
                or attempt >= max_attempts
            ):
                break
            retry_reason = (
                "; ".join(
                    str(reason)
                    for reason in state.guard_result.get("reasons", [])
                    if reason
                )
                if edge == "guard_failed"
                else state.verification_result.get("stderr", "verification failed")
            )
            state.metadata["attempt_failures"].append(
                {
                    "attempt": attempt,
                    "reason": retry_reason,
                    "provider": state.llm_output.get("provider"),
                    "edge": edge,
                }
            )
            state.metadata["retry_reason"] = retry_reason

        state = self._nodes.evaluator.run(state)
        state.metadata["edge"] = determine_next_edge(state)

        if self._nodes.reflection is not None:
            state = await self._nodes.reflection.run(state)

        return state


class LangGraphExecutorAdapter:
    def __init__(self, nodes: GraphNodes) -> None:
        self._nodes = nodes
        self._internal = InternalGraphExecutor(nodes)
        self._compiled_graph = None

    async def run(self, state: GraphState) -> GraphState:
        if graph_runtime_name() != "langgraph":
            state = await self._internal.run(state)
            state.metadata["orchestration_runtime"] = "internal"
            return state

        compiled = self._compiled_graph or self._build_compiled_graph()
        self._compiled_graph = compiled
        result = await compiled.ainvoke(state)
        if isinstance(result, GraphState):
            result.metadata["orchestration_runtime"] = "langgraph"
            return result
        validated = GraphState.model_validate(result)
        validated.metadata["orchestration_runtime"] = "langgraph"
        return validated

    def _build_compiled_graph(self):
        state_graph_cls = load_langgraph_state_graph()
        if state_graph_cls is None:
            raise RuntimeError(
                "LangGraph runtime requested but StateGraph is unavailable"
            )

        workflow = state_graph_cls(GraphState)
        workflow.add_node("internal_executor", self._internal.run)
        workflow.set_entry_point("internal_executor")
        workflow.set_finish_point("internal_executor")
        return workflow.compile()
