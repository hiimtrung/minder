import uuid
from pathlib import Path

import pytest

from minder.config import MinderConfig
from minder.graph import MinderGraph
from minder.graph.nodes import LLMNode, VerificationNode, WorkflowPlannerNode
from minder.llm.openai import OpenAIFallbackLLM
from minder.llm.qwen import QwenLocalLLM
from minder.store.error import ErrorStore
from minder.store.history import HistoryStore
from minder.store.relational import RelationalStore
from minder.tools.query import QueryTools

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


class FakeDockerRunner:
    def run_python(self, code: str, timeout_seconds: int, repo_path: str | None) -> dict[str, object]:
        return {
            "passed": True,
            "returncode": 0,
            "stdout": code,
            "stderr": "",
            "runner": "docker",
            "timeout_seconds": timeout_seconds,
            "repo_path": repo_path,
            "failure_kind": None,
            "retryable": False,
        }


class FailOnceDockerRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run_python(self, code: str, timeout_seconds: int, repo_path: str | None) -> dict[str, object]:
        self.calls += 1
        if self.calls == 1:
            return {
                "passed": False,
                "returncode": 1,
                "stdout": "",
                "stderr": "first run failed",
                "runner": "docker",
                "timeout_seconds": timeout_seconds,
                "repo_path": repo_path,
                "failure_kind": "container_error",
                "retryable": False,
            }
        return {
            "passed": True,
            "returncode": 0,
            "stdout": "ok",
            "stderr": "",
            "runner": "docker",
            "timeout_seconds": timeout_seconds,
            "repo_path": repo_path,
            "failure_kind": None,
            "retryable": False,
        }


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    settings = MinderConfig()
    settings.verification.sandbox = "docker"
    settings.llm.openai_api_key = "test-key"
    return settings


async def _seed(
    store: RelationalStore, repo_path: Path
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    user = await store.create_user(
        id=uuid.uuid4(),
        email="phase2x@example.com",
        username="phase2x",
        display_name="Phase 2.x",
        api_key_hash="hash",
        role="member",
        is_active=True,
        settings={},
    )
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
        repo_name="phase2x-repo",
        repo_url="https://example.com/phase2x",
        default_branch="main",
        workflow_id=workflow.id,
        state_path=str(repo_path / ".minder"),
        context_snapshot={},
        relationships={},
    )
    session = await store.create_session(
        id=uuid.uuid4(),
        user_id=user.id,
        repo_id=repo.id,
        project_context={},
        active_skills={},
        state={},
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
    return user.id, repo.id, session.id


@pytest.mark.asyncio
async def test_phase2x_gate(tmp_path: Path, store: RelationalStore, config: MinderConfig) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "feature.py").write_text("def work():\n    return 'ok'\n", encoding="utf-8")
    user_id, repo_id, session_id = await _seed(store, repo_path)

    retry_runner = FailOnceDockerRunner()
    graph = MinderGraph(
        store,
        config,
        workflow_planner=WorkflowPlannerNode(store),
        llm=LLMNode(
            primary=QwenLocalLLM(config.llm.model_path, runtime="auto"),
            fallback=OpenAIFallbackLLM(config.llm.openai_api_key, config.llm.openai_model),
        ),
        verification=VerificationNode(sandbox="docker", docker_runner=retry_runner),
        history_store=HistoryStore(store),
        error_store=ErrorStore(store),
    )
    tools = QueryTools(store, config, graph=graph)

    result = await tools.minder_query(
        "write tests for work",
        repo_path=str(repo_path),
        user_id=user_id,
        repo_id=repo_id,
        session_id=session_id,
        workflow_name="tdd",
        verification_payload={"language": "python", "code": "print('ok')"},
    )

    assert result["provider"] == "qwen_local"
    assert result["runtime"] in {"auto", "mock", "llama_cpp"}
    assert result["transition_log"]
    assert result["transition_log"][0]["edge"] == "verification_failed"
    assert result["transition_log"][-1]["edge"] == "complete"
    assert result["verification_result"]["runner"] == "docker"
    assert result["verification_result"]["failure_kind"] is None

    code_hits = await tools.minder_search_code("work", repo_path=str(repo_path))
    assert code_hits[0]["source_type"] == "code"
    assert code_hits[0]["path"].endswith("feature.py")

    fallback_graph = MinderGraph(
        store,
        config,
        llm=LLMNode(
            primary=QwenLocalLLM(config.llm.model_path, fail=True),
            fallback=OpenAIFallbackLLM(config.llm.openai_api_key, config.llm.openai_model),
        ),
        verification=VerificationNode(sandbox="docker", docker_runner=FakeDockerRunner()),
        history_store=HistoryStore(store),
        error_store=ErrorStore(store),
    )
    fallback_tools = QueryTools(store, config, graph=fallback_graph)
    fallback_result = await fallback_tools.minder_query(
        "explain work",
        repo_path=str(repo_path),
        user_id=user_id,
        repo_id=repo_id,
        session_id=session_id,
        workflow_name="tdd",
    )
    assert fallback_result["provider"] == "openai_fallback"
    assert fallback_result["edge"] == "fallback_complete"
    assert fallback_result["runtime"] in {"mock", "litellm"}

    history_entries = await HistoryStore(store).list_history_for_session(session_id)
    assert history_entries
    assert history_entries[-1].tool_calls["provider"] in {"qwen_local", "openai_fallback"}

    error_hits = await ErrorStore(store).search_errors("first run failed")
    assert error_hits
