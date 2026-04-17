import uuid
from pathlib import Path

import pytest

from minder.config import MinderConfig
from minder.graph import MinderGraph
from minder.graph.nodes import LLMNode, VerificationNode, WorkflowPlannerNode
from minder.llm.local import LocalModelLLM
from minder.llm.openai import OpenAIFallbackLLM
from minder.store.graph import KnowledgeGraphStore
from minder.store.error import ErrorStore
from minder.store.history import HistoryStore
from minder.store.relational import RelationalStore
from minder.tools.graph import GraphTools
from minder.tools.query import QueryTools

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


class UnsafeLLM:
    def generate(self, state):  # noqa: ANN001, ANN201
        return {"text": "steal credentials", "sources": []}


class FakeDockerRunner:
    def run_python(
        self, code: str, timeout_seconds: int, repo_path: str | None
    ) -> dict[str, object]:
        return {
            "passed": True,
            "returncode": 0,
            "stdout": code,
            "stderr": "",
            "runner": "docker",
            "timeout_seconds": timeout_seconds,
            "repo_path": repo_path,
        }


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
async def graph_store() -> KnowledgeGraphStore:
    backend = KnowledgeGraphStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    settings = MinderConfig()
    settings.verification.sandbox = "docker"
    settings.llm.openai_api_key = "test-key"
    return settings


async def _seed_workflow_context(
    store: RelationalStore, repo_path: Path
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    user = await store.create_user(
        id=uuid.uuid4(),
        email="phase2@example.com",
        username="phase2",
        display_name="Phase 2",
        api_key_hash="hash",
        role="member",
        is_active=True,
        settings={},
    )
    workflow = await store.create_workflow(
        id=uuid.uuid4(),
        name="tdd",
        version=1,
        steps=[
            {"name": "Test Writing"},
            {"name": "Implementation"},
            {"name": "Verification"},
        ],
        policies={"block_step_skips": True},
        default_for_repo=True,
    )
    repo = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="phase2-repo",
        repo_url="https://example.com/phase2",
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
async def test_phase2_gate(
    tmp_path: Path, store: RelationalStore, config: MinderConfig
) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    user_id, repo_id, session_id = await _seed_workflow_context(store, repo_path)

    graph = MinderGraph(
        store,
        config,
        workflow_planner=WorkflowPlannerNode(store),
        llm=LLMNode(
            primary=LocalModelLLM(config.llm.model_path),
            fallback=OpenAIFallbackLLM(
                config.llm.openai_api_key, config.llm.openai_model
            ),
        ),
        verification=VerificationNode(
            sandbox="docker", docker_runner=FakeDockerRunner()
        ),
        history_store=HistoryStore(store),
        error_store=ErrorStore(store),
    )
    tools = QueryTools(store, config, graph=graph)

    result = await tools.minder_query(
        "write tests for add and explain the implementation path",
        repo_path=str(repo_path),
        user_id=user_id,
        repo_id=repo_id,
        session_id=session_id,
        workflow_name="tdd",
        verification_payload={"language": "python", "code": "print('sandbox-ok')"},
    )

    assert "Answer:" in result["answer"]
    assert result["sources"]
    assert "Current step: Test Writing" in result["answer"]
    assert result["verification_result"]["runner"] == "docker"
    assert result["verification_result"]["passed"] is True

    unsafe_graph = MinderGraph(
        store,
        config,
        llm=LLMNode(primary=UnsafeLLM()),
        history_store=HistoryStore(store),
        error_store=ErrorStore(store),
    )
    unsafe_tools = QueryTools(store, config, graph=unsafe_graph)
    unsafe_result = await unsafe_tools.minder_query(
        "produce unsafe output",
        repo_path=str(repo_path),
        user_id=user_id,
        repo_id=repo_id,
        session_id=session_id,
        workflow_name="tdd",
    )
    assert unsafe_result["guard_result"]["passed"] is False

    workflow_state = await store.get_workflow_state_by_repo(repo_id)
    assert workflow_state is not None
    assert "Test Writing" in workflow_state.completed_steps
    assert workflow_state.current_step == "Implementation"

    history_entries = await HistoryStore(store).list_history_for_session(session_id)
    assert len(history_entries) >= 2

    errors = await ErrorStore(store).search_errors("unsafe output")
    assert errors

    code_hits = await tools.minder_search_code(
        "add implementation", repo_path=str(repo_path)
    )
    assert code_hits

    error_hits = await tools.minder_search_errors("unsafe")
    assert error_hits


@pytest.mark.asyncio
async def test_minder_query_includes_cross_repo_landscape_context(
    tmp_path: Path,
    store: RelationalStore,
    graph_store: KnowledgeGraphStore,
    config: MinderConfig,
) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    linked_repo_path = tmp_path / "linked-repo"
    linked_repo_path.mkdir()
    (repo_path / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    user_id, repo_id, session_id = await _seed_workflow_context(store, repo_path)
    repo = await store.get_repository_by_id(repo_id)
    assert repo is not None
    linked_repo = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="linked-repo",
        repo_url="https://example.com/linked-repo",
        default_branch="main",
        tracked_branches=["main"],
        state_path=str(linked_repo_path / ".minder"),
        context_snapshot={},
        relationships={},
    )
    await store.update_repository(
        repo_id,
        relationships={
            "cross_repo_branches": [
                {
                    "id": "phase2-link-main",
                    "source_repo_id": str(repo.id),
                    "source_repo_name": repo.repo_name,
                    "source_branch": "main",
                    "target_repo_id": str(linked_repo.id),
                    "target_repo_name": linked_repo.repo_name,
                    "target_branch": "main",
                    "relation": "depends_on",
                    "direction": "outbound",
                    "confidence": 1.0,
                }
            ]
        },
    )
    await graph_store.upsert_node(
        node_type="function",
        name="linked.py::add_consumer",
        metadata={
            "project": linked_repo.repo_name,
            "path": "linked.py",
            "symbol": "add_consumer",
        },
        repo_id=str(linked_repo.id),
        branch="main",
    )

    graph = MinderGraph(
        store,
        config,
        workflow_planner=WorkflowPlannerNode(store),
        llm=LLMNode(
            primary=LocalModelLLM(config.llm.model_path),
            fallback=OpenAIFallbackLLM(
                config.llm.openai_api_key, config.llm.openai_model
            ),
        ),
        verification=VerificationNode(
            sandbox="docker", docker_runner=FakeDockerRunner()
        ),
        history_store=HistoryStore(store),
        error_store=ErrorStore(store),
    )
    tools = QueryTools(
        store,
        config,
        graph=graph,
        graph_tools=GraphTools(graph_store, store),
    )

    result = await tools.minder_query(
        "explain add impact",
        repo_path=str(repo_path),
        user_id=user_id,
        repo_id=repo_id,
        session_id=session_id,
        workflow_name="tdd",
        verification_payload={"language": "python", "code": "print('sandbox-ok')"},
    )

    assert "Cross-repo landscape context is available" in result["answer"]
    assert result["cross_repo_graph"] is not None
    assert result["cross_repo_graph"]["scope_count"] == 2
