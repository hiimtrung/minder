import uuid
from pathlib import Path
import subprocess

import pytest

from minder.graph.executor import GraphNodes, InternalGraphExecutor
from minder.graph.nodes import (
    DockerSandboxRunner,
    GuardNode,
    LLMNode,
    PlanningNode,
    ReasoningNode,
    RetrieverNode,
    VerificationNode,
    WorkflowPlannerNode,
)
from minder.graph.nodes.evaluator import EvaluatorNode
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
    session = await store.create_session(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        repo_id=repo.id,
        project_context={"repo_path": "/tmp/demo", "branch": "main"},
        active_skills={"testing": True},
        state={"task": "Write tests", "next_steps": ["Draft failing tests"]},
        ttl=3600,
    )
    await store.create_workflow_state(
        id=uuid.uuid4(),
        repo_id=repo.id,
        session_id=session.id,
        current_step="Test Writing",
        completed_steps=[],
        blocked_by=[],
        artifacts={},
    )

    state = GraphState(
        query="implement feature", repo_id=repo.id, session_id=session.id
    )
    planned = await WorkflowPlannerNode(store).run(state)
    assert planned.workflow_context["current_step"] == "Test Writing"
    assert "Write tests before implementation" in planned.workflow_context["guidance"]
    assert (
        planned.workflow_context["instruction_envelope"]["current_step"]
        == "Test Writing"
    )
    assert (
        planned.workflow_context["continuity_brief"]["problem_framing"]["task"]
        == "Write tests"
    )


@pytest.mark.asyncio
async def test_planning_and_reasoning_nodes(tmp_path: Path) -> None:
    file_path = tmp_path / "service.py"
    file_path.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    state = GraphState(
        query="implement add tests",
        repo_path=str(tmp_path),
        workflow_context={
            "guidance": "Current step: Test Writing. Write tests before implementation.",
            "instruction_envelope": {
                "current_step": "Test Writing",
                "required_artifacts": ["test_plan"],
            },
            "continuity_brief": {"next_valid_actions": ["Write failing tests first"]},
        },
    )

    state = PlanningNode().run(state)
    state = await RetrieverNode(top_k=3).run(state)
    state = ReasoningNode().run(state)

    assert state.plan["intent"] == "code_gen"
    assert state.retrieved_docs[0]["path"] == str(file_path)
    assert "Current step: Test Writing" in state.reasoning_output["prompt"]
    assert "Instruction envelope:" in state.reasoning_output["prompt"]
    assert "Continuity packet:" in state.reasoning_output["prompt"]
    assert state.reasoning_output["prompt_name"] == "query_reasoning"


def test_reasoning_node_uses_custom_query_prompt_template() -> None:
    state = GraphState(
        query="explain the bug",
        workflow_context={
            "guidance": "Follow workflow instructions.",
            "instruction_envelope": {"current_step": "Review"},
            "continuity_brief": {"next_valid_actions": ["List blocking issues"]},
        },
        metadata={
            "query_prompt_name": "query_reasoning_override",
            "query_prompt_template": "Question={user_query}\nPacket={continuity_packet}\nFix={correction_required}",
        },
    )

    reasoned = ReasoningNode().run(state)

    assert "Question=explain the bug" in reasoned.reasoning_output["prompt"]
    assert '"next_valid_actions"' in reasoned.reasoning_output["prompt"]
    assert reasoned.reasoning_output["prompt_name"] == "query_reasoning_override"


def test_guard_blocks_unsafe_output() -> None:
    state = GraphState(query="unsafe")
    state.reranked_docs = [
        {"path": "/tmp/source.py", "title": "source.py", "score": 1.0}
    ]
    state.llm_output = {
        "text": "Run rm -rf / and use source /tmp/source.py",
        "sources": ["/tmp/source.py"],
    }

    guarded = GuardNode().run(state)
    assert guarded.guard_result["passed"] is False
    assert "unsafe pattern detected: rm -rf" in guarded.guard_result["reasons"][0]


def test_guard_enforces_workflow_output_contract() -> None:
    state = GraphState(query="workflow")
    state.workflow_context = {
        "instruction_envelope": {
            "output_contract": {
                "must_include": ["blocking_issues", "recommended_changes"]
            }
        }
    }
    state.llm_output = {
        "text": "This review only mentions recommended changes.",
        "sources": [],
    }

    guarded = GuardNode().run(state)
    assert guarded.guard_result["passed"] is False
    assert (
        "workflow output contract missing: blocking issues"
        in guarded.guard_result["reasons"]
    )


@pytest.mark.asyncio
async def test_internal_executor_retries_after_guard_failure(
    store: RelationalStore,
) -> None:
    class PassthroughWorkflowPlanner:
        async def run(self, state: GraphState) -> GraphState:
            return state

    class RetryAwareLLM:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, state: GraphState) -> dict[str, object]:
            self.calls += 1
            text = "recommended changes only"
            if state.metadata.get("retry_reason"):
                text = "blocking issues resolved and recommended changes included"
            return {
                "text": text,
                "sources": [],
                "provider": "test_llm",
                "model": "test",
                "runtime": "mock",
            }

    llm = RetryAwareLLM()
    state = GraphState(
        query="review change",
        metadata={"max_attempts": 2},
        workflow_context={
            "instruction_envelope": {
                "output_contract": {
                    "must_include": ["blocking_issues", "recommended_changes"]
                }
            },
            "guidance": "Review the change.",
        },
    )
    nodes = GraphNodes(
        workflow_planner=PassthroughWorkflowPlanner(),
        planning=PlanningNode(),
        retriever=RetrieverNode(top_k=1),
        reasoning=ReasoningNode(),
        llm=LLMNode(primary=llm),
        guard=GuardNode(),
        verification=VerificationNode(sandbox="subprocess"),
        evaluator=EvaluatorNode(),
    )

    result = await InternalGraphExecutor(nodes).run(state)

    assert llm.calls == 2
    assert result.guard_result["passed"] is True
    assert result.transition_log[0]["edge"] == "guard_failed"


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


def test_verification_normalizes_unsupported_language() -> None:
    state = GraphState(query="verify", repo_path=".")
    state.metadata["verification_payload"] = {
        "language": "javascript",
        "code": "console.log('ok')",
    }
    verified = VerificationNode(sandbox="docker").run(state)
    assert verified.verification_result["failure_kind"] == "unsupported_language"
    assert verified.verification_result["retryable"] is False


def test_subprocess_runner_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = VerificationNode(sandbox="subprocess")

    def fake_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise subprocess.TimeoutExpired(cmd=["python"], timeout=1)

    monkeypatch.setattr("minder.graph.nodes.verification.subprocess.run", fake_run)
    state = GraphState(query="verify", repo_path=".")
    state.metadata["verification_payload"] = {
        "language": "python",
        "code": "print('ok')",
    }
    verified = runner.run(state)
    assert verified.verification_result["failure_kind"] == "timeout"
    assert verified.verification_result["returncode"] == 124


def test_docker_runner_reports_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("minder.graph.nodes.verification.shutil.which", lambda _: None)
    result = DockerSandboxRunner().run_python("print('ok')", 5, ".")
    assert result["failure_kind"] == "docker_unavailable"
    assert result["passed"] is False
