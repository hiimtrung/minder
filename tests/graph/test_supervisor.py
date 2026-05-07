from __future__ import annotations

import uuid

import pytest

from minder.config import MinderConfig
from minder.graph.executor import GraphNodes, LangGraphExecutorAdapter
from minder.graph.nodes import ClarificationNode, GuardNode, PlanningNode
from minder.graph.state import GraphState
from minder.store.relational import RelationalStore


class _WorkflowPlannerNode:
    async def run(self, state: GraphState) -> GraphState:
        state.workflow_context["current_step"] = "review"
        return state


class _RetrieverNode:
    async def run(self, state: GraphState) -> GraphState:
        agent_name = str(state.metadata.get("agent_name", "fallback") or "fallback")
        state.retrieved_docs = [
            {
                "path": f"{agent_name}.md",
                "title": f"{agent_name} doc",
                "content": f"context for {agent_name}",
                "score": 0.8,
            }
        ]
        return state


class _ReasoningNode:
    def run(self, state: GraphState) -> GraphState:
        docs = list(state.retrieved_docs or [])
        agent_name = str(state.metadata.get("agent_name", "fallback") or "fallback")
        state.reasoning_output = {
            "prompt": f"prompt for {agent_name}",
            "sources": [{"path": doc["path"], "score": doc["score"]} for doc in docs],
        }
        return state


class _LLMNode:
    def run(self, state: GraphState) -> GraphState:
        agent_name = str(state.metadata.get("agent_name", "fallback") or "fallback")
        state.llm_output = {
            "text": f"handled by {agent_name}",
            "provider": "test",
            "model": "test-double",
            "runtime": "fake",
        }
        return state


class _VerificationNode:
    def run(self, state: GraphState) -> GraphState:
        state.verification_result = {"passed": True}
        return state


class _EvaluatorNode:
    def run(self, state: GraphState) -> GraphState:
        state.evaluation = {"score": 1.0}
        return state


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore("sqlite+aiosqlite:///:memory:")
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.mark.asyncio
async def test_supervisor_routes_review_queries_to_review_agent(
    store: RelationalStore,
) -> None:
    await store.upsert_agent(
        "code_reviewer",
        title="Code Reviewer",
        description="Reviews changes",
        system_prompt="review prompt",
        tools=["minder_search_code"],
        workflow_steps=["review"],
        artifact_types=["review_notes"],
        tags=["review"],
        is_default=False,
    )
    await store.upsert_agent(
        "tester",
        title="Tester",
        description="Writes tests",
        system_prompt="test prompt",
        tools=["minder_search_code"],
        workflow_steps=["write_tests"],
        artifact_types=["test_plan"],
        tags=["testing"],
        is_default=False,
    )

    adapter = LangGraphExecutorAdapter(
        GraphNodes(
            workflow_planner=_WorkflowPlannerNode(),
            planning=PlanningNode(),
            clarification=ClarificationNode(),
            retriever=_RetrieverNode(),
            reasoning=_ReasoningNode(),
            llm=_LLMNode(),
            guard=GuardNode(),
            verification=_VerificationNode(),
            evaluator=_EvaluatorNode(),
        ),
        store,
        MinderConfig(),
    )

    result = await adapter.run(
        GraphState(
            query="review this change for regressions",
            session_id=uuid.uuid4(),
            metadata={"max_attempts": 1},
        )
    )

    assert result.metadata["supervisor_used"] is True
    assert result.metadata["supervisor_selected_agent"] == "code_reviewer"
    assert result.llm_output["text"] == "handled by code_reviewer"
    assert result.reranked_docs[0]["path"] == "code_reviewer.md"
