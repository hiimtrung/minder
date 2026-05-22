from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import inspect
import uuid
from typing import Any

from minder.config import MinderConfig
from minder.graph.checkpoint import MinderCheckpointSaver
from minder.graph.concurrency import run_in_thread
from minder.graph.edges import determine_next_edge
from minder.graph.nodes import (
    ClarificationNode,
    ContextEnricherNode,
    EvaluatorNode,
    GuardNode,
    LLMNode,
    PlanningNode,
    ParallelRetrieverNode,
    ReasoningNode,
    RerankerNode,
    ReflectionNode,
    RetrieverNode,
    VerificationNode,
    WorkflowPlannerNode,
)
from minder.graph.runtime import graph_runtime_name, load_langgraph_state_graph
from minder.graph.state import GraphState, GraphStateSchema
from minder.graph.supervisor import AgentSupervisor
from minder.store.interfaces import IOperationalStore


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
    context_enricher: ContextEnricherNode | None = field(default=None)


class InternalGraphExecutor:
    def __init__(self, nodes: GraphNodes) -> None:
        self._nodes = nodes

    async def run(self, state: GraphState) -> GraphState:
        max_attempts = int(state.metadata.get("max_attempts", 1))
        state.metadata.setdefault("attempt_failures", [])
        state.metadata["orchestration_runtime"] = "internal"
        state = await self._nodes.workflow_planner.run(state)
        # Fast sync nodes — run in thread to yield control to the event loop
        state = await run_in_thread(self._nodes.planning.run, state)
        state = await run_in_thread(self._nodes.clarification.run, state)
        if state.metadata.get("needs_clarification"):
            return state
        state = await self._nodes.retriever.run(state)
        if self._nodes.reranker is not None:
            state = await self._nodes.reranker.run(state)
        if self._nodes.context_enricher is not None:
            state = await self._nodes.context_enricher.run(state)

        attempt = 0
        while True:
            attempt += 1
            state.retry_count = attempt - 1
            # reasoning builds the prompt (CPU-bound string work)
            state = await run_in_thread(self._nodes.reasoning.run, state)
            # LLM inference is the main bottleneck — run in dedicated thread
            # with semaphore + timeout so other requests keep moving
            state = await run_in_thread(
                self._nodes.llm.run,
                state,
                use_llm_semaphore=True,
            )
            state = await run_in_thread(self._nodes.guard.run, state)
            state = await run_in_thread(self._nodes.verification.run, state)
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

        state = await run_in_thread(self._nodes.evaluator.run, state)
        state.metadata["edge"] = determine_next_edge(state)

        if self._nodes.reflection is not None:
            state = await self._nodes.reflection.run(state)

        return state


class LangGraphExecutorAdapter:
    def __init__(
        self,
        nodes: GraphNodes,
        store: IOperationalStore,
        config: MinderConfig | None = None,
        *,
        graph_tools: Any | None = None,
    ) -> None:
        self._nodes = nodes
        self._internal = InternalGraphExecutor(nodes)
        self._store = store
        self._config = config
        self._graph_tools = graph_tools
        self._checkpointer = MinderCheckpointSaver(store)
        self._compiled_graph = None
        self._supervisor: AgentSupervisor | None = None

    async def run(self, state: GraphState) -> GraphState:
        if graph_runtime_name() != "langgraph":
            state = await self._internal.run(state)
            state.metadata["orchestration_runtime"] = "internal"
            return state

        compiled = await self._ensure_compiled_graph()
        state.metadata.setdefault("attempt_failures", [])
        config = {
            "configurable": {
                "thread_id": str(state.session_id) if state.session_id else "default"
            }
        }
        result = await compiled.ainvoke(state.model_dump(mode="python"), config)
        return self._coerce_state(state, result)

    async def astream_events(
        self, state: GraphState, config: dict[str, Any], version: str = "v2"
    ) -> Any:
        if graph_runtime_name() != "langgraph":
            raise RuntimeError(
                "astream_events is only supported when graph runtime is langgraph"
            )
        compiled = await self._ensure_compiled_graph()
        async for event in compiled.astream_events(
            state.model_dump(mode="python"), config, version=version
        ):
            yield event

    async def resume(self, session_id: uuid.UUID, decision: dict[str, Any]) -> GraphState:
        if graph_runtime_name() != "langgraph":
            raise RuntimeError("resume is only supported when graph runtime is langgraph")
        compiled = await self._ensure_compiled_graph()
        config = {"configurable": {"thread_id": str(session_id)}}
        result = await compiled.ainvoke(self._resume_command(decision), config)
        return self._coerce_state(GraphState(query="", session_id=session_id), result)

    async def _build_compiled_graph(self):
        state_graph_cls = load_langgraph_state_graph()
        if state_graph_cls is None:
            raise RuntimeError(
                "LangGraph runtime requested but StateGraph is unavailable"
            )

        workflow = state_graph_cls(GraphStateSchema)
        supervisor = await self._build_supervisor()
        has_supervisor = bool(supervisor and supervisor.has_agents)

        workflow.add_node(
            "workflow_planner", self._wrap_state_handler(self._nodes.workflow_planner.run)
        )
        workflow.add_node("planning", self._wrap_state_handler(self._nodes.planning.run))
        workflow.add_node(
            "clarification", self._wrap_state_handler(self._nodes.clarification.run)
        )
        if has_supervisor and supervisor is not None:
            workflow.add_node(
                "supervisor", self._wrap_state_handler(supervisor.supervisor_entry)
            )
            for destination in supervisor.destinations():
                workflow.add_node(
                    destination,
                    supervisor.make_agent_node(destination.removeprefix("agent_")),
                )
            workflow.add_node(
                "aggregate_agents",
                self._wrap_state_handler(supervisor.aggregate_agent_outputs),
            )

        enable_parallel = (
            getattr(self._config.graph, "enable_parallel_retrieval", False)
            if self._config
            else False
        )
        if enable_parallel:
            parallel_retriever = ParallelRetrieverNode(
                self._nodes.retriever, self._config, graph_tools=self._graph_tools
            )
            workflow.add_node(
                "plan_retrieval",
                self._wrap_state_handler(lambda state: state),
            )
            workflow.add_node(
                "retrieve_strategy",
                self._wrap_state_handler(parallel_retriever.retrieve_strategy),
            )
            workflow.add_node(
                "merge_retrieved",
                self._wrap_state_handler(parallel_retriever.merge_retrieved),
            )
        else:
            workflow.add_node(
                "retriever", self._wrap_state_handler(self._nodes.retriever.run)
            )

        if self._nodes.reranker is not None:
            workflow.add_node(
                "reranker", self._wrap_state_handler(self._nodes.reranker.run)
            )

        if self._nodes.context_enricher is not None:
            workflow.add_node(
                "context_enricher",
                self._wrap_state_handler(self._nodes.context_enricher.run),
            )

        workflow.add_node(
            "reasoning", self._wrap_state_handler(self._node_reasoning_wrapper)
        )
        workflow.add_node("llm", self._wrap_state_handler(self._nodes.llm.run))
        workflow.add_node("guard", self._wrap_state_handler(self._nodes.guard.run))
        workflow.add_node(
            "verification", self._wrap_state_handler(self._nodes.verification.run)
        )
        workflow.add_node(
            "evaluator", self._wrap_state_handler(self._nodes.evaluator.run)
        )
        if self._nodes.reflection is not None:
            workflow.add_node(
                "reflection", self._wrap_state_handler(self._nodes.reflection.run)
            )

        workflow.set_entry_point("workflow_planner")
        workflow.add_edge("workflow_planner", "planning")
        workflow.add_edge("planning", "clarification")

        def clarification_router(state: dict[str, Any]) -> str:
            graph_state = GraphState.model_validate(state)
            if graph_state.metadata.get("needs_clarification"):
                return "END"
            if has_supervisor:
                return "supervisor"
            return "plan_retrieval" if enable_parallel else "retriever"

        clarification_edges = {"END": "__end__"}
        if has_supervisor:
            clarification_edges["supervisor"] = "supervisor"
        if enable_parallel:
            clarification_edges["plan_retrieval"] = "plan_retrieval"
        else:
            clarification_edges["retriever"] = "retriever"

        workflow.add_conditional_edges(
            "clarification", clarification_router, clarification_edges
        )

        if has_supervisor and supervisor is not None:
            supervisor_edges = {
                destination: destination for destination in supervisor.destinations()
            }
            supervisor_edges["fallback_retrieval"] = (
                "plan_retrieval" if enable_parallel else "retriever"
            )
            workflow.add_conditional_edges(
                "supervisor",
                self._wrap_router(supervisor.supervisor_router),
                supervisor_edges,
            )
            for destination in supervisor.destinations():
                workflow.add_edge(destination, "aggregate_agents")
            workflow.add_edge("aggregate_agents", "guard")

        if enable_parallel:
            workflow.add_conditional_edges(
                "plan_retrieval",
                self._wrap_router(parallel_retriever.plan_retrieval),
                ["retrieve_strategy"],
            )
            workflow.add_edge("retrieve_strategy", "merge_retrieved")
            retrieval_end_node = "merge_retrieved"
        else:
            retrieval_end_node = "retriever"

        has_enricher = self._nodes.context_enricher is not None
        if self._nodes.reranker is not None:
            workflow.add_edge(retrieval_end_node, "reranker")
            post_retrieval_node = "reranker"
        else:
            post_retrieval_node = retrieval_end_node

        if has_enricher:
            workflow.add_edge(post_retrieval_node, "context_enricher")
            workflow.add_edge("context_enricher", "reasoning")
        else:
            workflow.add_edge(post_retrieval_node, "reasoning")

        workflow.add_edge("reasoning", "llm")
        workflow.add_edge("llm", "guard")
        workflow.add_edge("guard", "verification")

        def record_transition(state: dict[str, Any]) -> dict[str, Any]:
            graph_state = GraphState.model_validate(state)
            attempt = graph_state.retry_count + 1
            edge = determine_next_edge(graph_state)

            new_log = list(graph_state.transition_log)
            new_log.append(
                {
                    "attempt": attempt,
                    "edge": edge,
                    "provider": graph_state.llm_output.get("provider"),
                    "fallback_used": graph_state.metadata.get("fallback_used", False),
                }
            )
            graph_state.transition_log = new_log

            max_attempts = int(graph_state.metadata.get("max_attempts", 1))
            if edge in {"verification_failed", "guard_failed"} and attempt < max_attempts:
                retry_reason = (
                    "; ".join(
                        str(reason)
                        for reason in graph_state.guard_result.get("reasons", [])
                        if reason
                    )
                    if edge == "guard_failed"
                    else graph_state.verification_result.get(
                        "stderr", "verification failed"
                    )
                )
                if "attempt_failures" not in graph_state.metadata:
                    graph_state.metadata["attempt_failures"] = []

                graph_state.metadata["attempt_failures"].append(
                    {
                        "attempt": attempt,
                        "reason": retry_reason,
                        "provider": graph_state.llm_output.get("provider"),
                        "edge": edge,
                    }
                )
                graph_state.metadata["retry_reason"] = retry_reason
            return graph_state.model_dump(mode="python")

        workflow.add_node("record_transition", record_transition)
        workflow.add_edge("verification", "record_transition")

        def check_attempt_loop(state: dict[str, Any]) -> str:
            graph_state = GraphState.model_validate(state)
            max_attempts = int(graph_state.metadata.get("max_attempts", 1))
            attempt = graph_state.retry_count + 1
            edge = determine_next_edge(graph_state)
            if (
                edge not in {"verification_failed", "guard_failed"}
                or attempt >= max_attempts
            ):
                return "evaluator"
            if has_supervisor and graph_state.metadata.get("supervisor_used"):
                return "supervisor"
            return "reasoning"

        record_transition_edges = {"reasoning": "reasoning", "evaluator": "evaluator"}
        if has_supervisor:
            record_transition_edges["supervisor"] = "supervisor"
        workflow.add_conditional_edges(
            "record_transition", check_attempt_loop, record_transition_edges
        )

        if self._nodes.reflection is not None:
            workflow.add_edge("evaluator", "reflection")
            workflow.add_edge("reflection", "__end__")
        else:
            workflow.add_edge("evaluator", "__end__")

        compile_kwargs: dict[str, Any] = {}
        if self._config is None or self._config.graph.enable_checkpointing:
            compile_kwargs["checkpointer"] = self._checkpointer
        return workflow.compile(**compile_kwargs)

    def _node_reasoning_wrapper(self, state: GraphState) -> GraphState:
        if "attempt_failures" not in state.metadata:
            state.metadata["attempt_failures"] = []
        state.retry_count = len(state.metadata["attempt_failures"])
        return self._nodes.reasoning.run(state)

    async def _ensure_compiled_graph(self):
        if self._compiled_graph is None:
            self._compiled_graph = await self._build_compiled_graph()
        return self._compiled_graph

    async def _build_supervisor(self) -> AgentSupervisor | None:
        supervisor = AgentSupervisor(
            self._store, self._nodes, self._config, graph_tools=self._graph_tools
        )
        await supervisor.initialize()
        if not supervisor.has_agents:
            return None
        self._supervisor = supervisor
        return supervisor

    def _coerce_state(self, original_state: GraphState, result: Any) -> GraphState:
        if isinstance(result, GraphState):
            validated = result
        else:
            payload = dict(result or {})
            interrupts = payload.pop("__interrupt__", None)
            validated = GraphState.model_validate(
                {
                    **original_state.model_dump(mode="python"),
                    **payload,
                }
            )
            if interrupts:
                validated.metadata["waiting_for_approval"] = True
                validated.metadata["interrupts"] = self._serialize_interrupts(interrupts)
                validated.metadata["edge"] = "waiting_approval"
        validated.metadata["orchestration_runtime"] = "langgraph"
        if not validated.metadata.get("waiting_for_approval"):
            validated.metadata["edge"] = determine_next_edge(validated)
        return validated

    @staticmethod
    def _resume_command(decision: dict[str, Any]) -> Any:
        from langgraph.types import Command

        return Command(resume=decision)

    @staticmethod
    def _serialize_interrupts(interrupts: Any) -> list[dict[str, Any]]:
        items = list(interrupts) if isinstance(interrupts, (list, tuple)) else [interrupts]
        return [
            {
                "id": getattr(item, "id", None),
                "value": getattr(item, "value", None),
            }
            for item in items
        ]

    @staticmethod
    def _wrap_state_handler(handler):  # noqa: ANN001
        is_async = inspect.iscoroutinefunction(handler)

        async def wrapped(state):  # noqa: ANN001
            graph_state = GraphState.model_validate(state)
            if is_async:
                result = await handler(graph_state)
            else:
                # Run blocking sync handlers in a thread pool to avoid
                # stalling the event loop during CPU-bound LLM inference.
                result = await asyncio.to_thread(handler, graph_state)
            if isinstance(result, GraphState):
                return dict(result)
            return result

        return wrapped

    @staticmethod
    def _wrap_router(router):  # noqa: ANN001
        def wrapped(state):  # noqa: ANN001
            return router(GraphState.model_validate(state))

        return wrapped
