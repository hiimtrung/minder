import uuid
from pathlib import Path

import pytest

from minder.graph.nodes import (
    DockerSandboxRunner,
    GuardNode,
    PlanningNode,
    ReasoningNode,
    RetrieverNode,
    VerificationNode,
    WorkflowPlannerNode,
)
from minder.graph.state import GraphState
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


async def test_workflow_planner_uses_repo_state(store: RelationalStore) -> None:
    workflow = await store.create_workflow(
        id=uuid.uuid4(),
        name="tdd",
        version=1,
        steps=[{"name": "Test Writing"}, {"name": "Implementation"}],
        policies={},
        default_for_repo=True,
    )
    repo = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="demo",
        repo_url="https://example.com/demo",
        default_branch="main",
        workflow_id=workflow.id,
        state_path=".minder",
        context_snapshot={},
        relationships={},
    )
    await store.create_workflow_state(
        id=uuid.uuid4(),
        repo_id=repo.id,
        current_step="Test Writing",
        completed_steps=[],
        blocked_by=[],
        artifacts={},
    )

    state = GraphState(query="implement feature", repo_id=repo.id)
    planned = await WorkflowPlannerNode(store).run(state)
    assert planned.workflow_context["current_step"] == "Test Writing"
    assert "Write tests before implementation" in planned.workflow_context["guidance"]


@pytest.mark.asyncio
async def test_planning_and_reasoning_nodes(tmp_path: Path) -> None:
    file_path = tmp_path / "service.py"
    file_path.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    state = GraphState(
        query="implement add tests",
        repo_path=str(tmp_path),
        workflow_context={
            "guidance": "Current step: Test Writing. Write tests before implementation."
        },
    )

    state = PlanningNode().run(state)
    state = await RetrieverNode(top_k=3).run(state)
    state = ReasoningNode().run(state)

    assert state.plan["intent"] == "code_gen"
    assert state.retrieved_docs[0]["path"] == str(file_path)
    assert "Current step: Test Writing" in state.reasoning_output["prompt"]


def test_guard_blocks_unsafe_output() -> None:
    state = GraphState(query="unsafe")
    state.reranked_docs = [{"path": "/tmp/source.py", "title": "source.py", "score": 1.0}]
    state.llm_output = {
        "text": "Run rm -rf / and use source /tmp/source.py",
        "sources": ["/tmp/source.py"],
    }

    guarded = GuardNode().run(state)
    assert guarded.guard_result["passed"] is False
    assert "unsafe pattern detected: rm -rf" in guarded.guard_result["reasons"][0]


def test_verification_subprocess_executes_python() -> None:
    state = GraphState(query="verify", repo_path=".")
    state.metadata["verification_payload"] = {
        "language": "python",
        "code": "print('ok')",
    }

    verified = VerificationNode(sandbox="subprocess").run(state)
    assert verified.verification_result["passed"] is True
    assert verified.verification_result["stdout"].strip() == "ok"


def test_verification_docker_runner_marks_docker_mode() -> None:
    state = GraphState(query="verify", repo_path=".")
    state.metadata["verification_payload"] = {
        "language": "python",
        "code": "print('ok')",
    }

    verified = VerificationNode(
        sandbox="docker",
        docker_runner=DockerSandboxRunner(),
    ).run(state)
    assert verified.verification_result["runner"] == "docker"
    assert "timeout_seconds" in verified.verification_result
