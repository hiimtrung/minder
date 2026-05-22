from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from time import perf_counter

from minder.config import MinderConfig
from minder.embedding.local import LocalEmbeddingProvider
from minder.graph import concurrency as _concurrency
from minder.graph.concurrency import run_in_thread, stream_sync_generator
from minder.graph.edges import determine_next_edge
from minder.graph.executor import (
    GraphNodes,
    InternalGraphExecutor,
    LangGraphExecutorAdapter,
)
from minder.graph.nodes import (
    ClarificationNode,
    ContextEnricherNode,
    EvaluatorNode,
    GuardNode,
    LLMNode,
    PlanningNode,
    ReasoningNode,
    RerankerNode,
    RetrieverNode,
    VerificationNode,
    WorkflowPlannerNode,
)
from minder.graph.state import GraphState
from minder.llm.factory import create_llm
from minder.llm.openai import OpenAIFallbackLLM
from minder.store.interfaces import (
    IOperationalStore,
    IErrorRepository,
    IHistoryRepository,
)


class MinderGraph:
    def __init__(
        self,
        store: IOperationalStore,
        config: MinderConfig,
        *,
        workflow_planner: WorkflowPlannerNode | None = None,
        planning: PlanningNode | None = None,
        clarification: ClarificationNode | None = None,
        retriever: RetrieverNode | None = None,
        reranker: RerankerNode | None = None,
        context_enricher: ContextEnricherNode | None = None,
        reasoning: ReasoningNode | None = None,
        llm: LLMNode | None = None,
        guard: GuardNode | None = None,
        verification: VerificationNode | None = None,
        evaluator: EvaluatorNode | None = None,
        history_store: IHistoryRepository | None = None,
        error_store: IErrorRepository | None = None,
        graph_tools: Any | None = None,
    ) -> None:
        from minder.store.vector import VectorStore

        self._store = store
        self._config = config
        self._workflow_planner = workflow_planner or WorkflowPlannerNode(store)
        self._planning = planning or PlanningNode()
        self._clarification = clarification or ClarificationNode()
        vector_store = VectorStore(store, store)
        embedder = LocalEmbeddingProvider(
            llama_cpp_model_repo=config.embedding.llama_cpp_model_repo,
            llama_cpp_model_file=config.embedding.llama_cpp_model_file,
            dimensions=config.embedding.dimensions,
            runtime="auto",
        )
        self._retriever = retriever or RetrieverNode(
            top_k=config.retrieval.top_k,
            embedding_provider=embedder,
            vector_store=vector_store,
            score_threshold=config.retrieval.similarity_threshold,
        )
        self._reranker = reranker  # None by default; pass RerankerNode(...) to activate
        self._context_enricher = context_enricher or ContextEnricherNode(store)
        self._reasoning = reasoning or ReasoningNode()
        self._llm = llm or LLMNode(
            primary=create_llm(config.llm),
            fallback=OpenAIFallbackLLM(
                config.llm.openai_api_key,
                config.llm.openai_model,
                runtime="auto",
            ),
        )
        self._guard = guard or GuardNode()
        self._verification = verification or VerificationNode(
            sandbox=config.verification.sandbox,
            timeout_seconds=config.verification.timeout_seconds,
        )
        self._evaluator = evaluator or EvaluatorNode()
        self._history_store = history_store or store
        self._error_store = error_store or store
        self._graph_tools = graph_tools
        self._cached_executor: InternalGraphExecutor | LangGraphExecutorAdapter | None = None
        # Apply LLM concurrency and timeout settings from config
        _concurrency.configure(
            max_concurrent=config.llm.max_concurrent,
            timeout_seconds=config.llm.timeout_seconds,
        )
        self._nodes = GraphNodes(
            workflow_planner=self._workflow_planner,
            planning=self._planning,
            clarification=self._clarification,
            retriever=self._retriever,
            reranker=self._reranker,
            context_enricher=self._context_enricher,
            reasoning=self._reasoning,
            llm=self._llm,
            guard=self._guard,
            verification=self._verification,
            evaluator=self._evaluator,
        )

    async def run(self, state: GraphState) -> GraphState:
        executor = self._select_executor()
        state = await executor.run(state)
        await self._finalize_state(state)
        return state

    async def astream_events(self, state: GraphState, config: dict[str, Any], version: str = "v2") -> AsyncGenerator[dict[str, Any], None]:
        executor = self._select_executor()
        if not hasattr(executor, "astream_events"):
            raise NotImplementedError("astream_events is only supported for langgraph runtime")
        async for event in executor.astream_events(state, config, version=version):
            yield event

    async def resume(self, session_id, decision: dict[str, Any]) -> GraphState:  # noqa: ANN001
        executor = self._select_executor()
        if not hasattr(executor, "resume"):
            raise NotImplementedError("resume is only supported for langgraph runtime")
        state = await executor.resume(session_id, decision)
        await self._finalize_state(state)
        return state

    async def stream(
        self, state: GraphState
    ) -> AsyncGenerator[dict[str, object], None]:
        max_attempts = int(state.metadata.get("max_attempts", 1))
        state.metadata.setdefault("attempt_failures", [])
        state.metadata["orchestration_runtime"] = "internal"
        state = await self._nodes.workflow_planner.run(state)
        state = self._nodes.planning.run(state)
        state = self._nodes.clarification.run(state)
        if state.metadata.get("needs_clarification"):
            yield {"type": "clarification", "options": state.metadata.get("clarification_options", [])}
            yield {"type": "final", "state": state}
            return
        state = await self._nodes.retriever.run(state)
        if self._nodes.reranker is not None:
            state = await self._nodes.reranker.run(state)
        if self._nodes.context_enricher is not None:
            state = await self._nodes.context_enricher.run(state)

        attempt = 0
        while True:
            attempt += 1
            state.retry_count = attempt - 1
            state = await run_in_thread(self._nodes.reasoning.run, state)
            yield {"type": "attempt", "attempt": attempt}
            # Stream LLM tokens without blocking the event loop.
            # stream_sync_generator runs the sync generator in the inference
            # thread pool and forwards items through an asyncio.Queue.
            async for event in stream_sync_generator(
                self._nodes.llm.stream,
                state,
                use_llm_semaphore=True,
            ):
                if str(event.get("type")) == "result":
                    # Capture the final LLM output written back to state
                    result_data = dict(event.get("result", {}) or {})
                    if result_data:
                        state.llm_output = result_data
                    continue
                yield {**event, "attempt": attempt}
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
            yield {
                "type": "retry",
                "attempt": attempt,
                "reason": retry_reason,
                "edge": edge,
            }

        state = await run_in_thread(self._nodes.evaluator.run, state)
        state.metadata["edge"] = determine_next_edge(state)
        await self._persist_history(state)
        await self._persist_error_if_needed(state)
        await self._advance_workflow_if_needed(state)
        yield {"type": "final", "state": state}

    def _select_executor(self) -> InternalGraphExecutor | LangGraphExecutorAdapter:
        if self._cached_executor is not None:
            return self._cached_executor
        if self._config.workflow.orchestration_runtime == "langgraph":
            self._cached_executor = LangGraphExecutorAdapter(
                self._nodes,
                self._store,
                self._config,
                graph_tools=self._graph_tools,
            )
        else:
            self._cached_executor = InternalGraphExecutor(self._nodes)
        return self._cached_executor

    async def _persist_history(self, state: GraphState) -> None:
        if state.session_id is None:
            return
        started = perf_counter()
        await self._history_store.create_history(
            session_id=state.session_id,
            role="assistant",
            content=str(state.llm_output.get("text", "")),
            reasoning_trace=str(state.reasoning_output.get("prompt", "")),
            tool_calls={
                "pipeline": [
                    "workflow_planner",
                    "planning",
                    "retriever",
                    "reasoning",
                    "llm",
                    "guard",
                    "verification",
                ],
                "transition_log": state.transition_log,
                "provider": state.llm_output.get("provider"),
                "fallback_used": state.metadata.get("fallback_used", False),
            },
            latency_ms=int((perf_counter() - started) * 1000),
        )

    async def _persist_error_if_needed(self, state: GraphState) -> None:
        reasons = list(state.guard_result.get("reasons", []))
        if state.verification_result.get("passed") is False:
            reasons.append(
                str(state.verification_result.get("stderr", "verification failed"))
            )
        for attempt_failure in state.metadata.get("attempt_failures", []):
            reasons.append(str(attempt_failure.get("reason", "attempt failed")))
        if not reasons:
            return
        await self._error_store.create_error(
            error_code="PIPELINE_FAILURE",
            error_message="; ".join(reason for reason in reasons if reason),
            context={
                "query": state.query,
                "repo_path": state.repo_path,
                "transition_log": state.transition_log,
                "provider": state.llm_output.get("provider"),
                "retry_count": state.retry_count,
            },
            resolved=False,
        )

    async def _advance_workflow_if_needed(self, state: GraphState) -> None:
        if state.repo_id is None:
            return
        if state.guard_result.get("passed") is not True:
            return
        if state.verification_result.get("passed") is not True:
            return
        workflow_state = await self._store.get_workflow_state_by_repo(state.repo_id)
        if workflow_state is None:
            return
        current_step = workflow_state.current_step
        completed_steps = list(workflow_state.completed_steps)
        if current_step not in completed_steps:
            completed_steps.append(current_step)
        await self._store.update_workflow_state(
            workflow_state.id,
            completed_steps=completed_steps,
            current_step=state.workflow_context.get("next_step") or current_step,
            next_step=None,
            artifacts={
                **dict(workflow_state.artifacts),
                "last_transition_reason": "guard+verification passed",
                "last_provider": state.llm_output.get("provider"),
                "last_edge": state.metadata.get("edge"),
            },
        )

    async def _finalize_state(self, state: GraphState) -> None:
        if state.metadata.get("waiting_for_approval"):
            return
        await self._persist_history(state)
        await self._persist_error_if_needed(state)
        await self._advance_workflow_if_needed(state)
