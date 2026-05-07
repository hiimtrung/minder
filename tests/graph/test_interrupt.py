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
        state.workflow_context.setdefault("current_step", "deploy")
        return state


class _RetrieverNode:
    async def run(self, state: GraphState) -> GraphState:
        state.retrieved_docs = [
            {
                "path": "deploy.md",
                "title": "Deploy playbook",
                "content": "Deploy to production only after explicit approval.",
                "score": 0.9,
            }
        ]
        return state


class _ReasoningNode:
    def run(self, state: GraphState) -> GraphState:
        state.reasoning_output = {
            "prompt": "deploy prompt",
            "sources": [{"path": "deploy.md", "score": 0.9}],
        }
        return state


class _LLMNode:
    def run(self, state: GraphState) -> GraphState:
        state.llm_output = {
            "text": "Deploy service X to prod with the approved checklist.",
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
async def test_langgraph_interrupt_and_resume(store: RelationalStore) -> None:
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
    session_id = uuid.uuid4()

    interrupted = await adapter.run(
        GraphState(
            query="deploy service X to prod",
            session_id=session_id,
            metadata={"max_attempts": 1},
        )
    )

    assert interrupted.metadata["waiting_for_approval"] is True
    assert interrupted.metadata["edge"] == "waiting_approval"
    assert interrupted.metadata["interrupts"][0]["value"]["type"] == "approval_required"

    resumed = await adapter.resume(
        session_id,
        {"approved": True, "comment": "LGTM"},
    )

    assert resumed.metadata.get("waiting_for_approval") is not True
    assert resumed.guard_result["passed"] is True
    assert resumed.guard_result["human_decision"]["approved"] is True
    assert resumed.verification_result["passed"] is True
