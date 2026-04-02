from __future__ import annotations

from dataclasses import dataclass

from minder.graph.edges import determine_next_edge
from minder.graph.nodes import (
    EvaluatorNode,
    GuardNode,
    LLMNode,
    PlanningNode,
    ReasoningNode,
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
    retriever: RetrieverNode
    reasoning: ReasoningNode
    llm: LLMNode
    guard: GuardNode
    verification: VerificationNode
    evaluator: EvaluatorNode


class InternalGraphExecutor:
    def __init__(self, nodes: GraphNodes) -> None:
        self._nodes = nodes

    async def run(self, state: GraphState) -> GraphState:
        max_attempts = int(state.metadata.get("max_attempts", 1))
        state.metadata.setdefault("attempt_failures", [])
        state.metadata["orchestration_runtime"] = "internal"
        state = await self._nodes.workflow_planner.run(state)
        state = self._nodes.planning.run(state)
        state = await self._nodes.retriever.run(state)

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
            if edge != "verification_failed" or attempt >= max_attempts:
                break
            state.metadata["attempt_failures"].append(
                {
                    "attempt": attempt,
                    "reason": state.verification_result.get(
                        "stderr", "verification failed"
                    ),
                    "provider": state.llm_output.get("provider"),
                }
            )
            state.metadata["retry_reason"] = state.verification_result.get(
                "stderr", "verification failed"
            )

        state = self._nodes.evaluator.run(state)
        state.metadata["edge"] = determine_next_edge(state)
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
            raise RuntimeError("LangGraph runtime requested but StateGraph is unavailable")

        workflow = state_graph_cls(GraphState)
        workflow.add_node("internal_executor", self._internal.run)
        workflow.set_entry_point("internal_executor")
        workflow.set_finish_point("internal_executor")
        return workflow.compile()
