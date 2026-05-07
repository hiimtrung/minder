from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from minder.config import MinderConfig
from minder.graph.session_graph import SessionContextGraph
from minder.store.relational import RelationalStore
from minder.tools.memory import MemoryTools
from minder.tools.session import SessionTools

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    settings = MinderConfig()
    settings.embedding.runtime = "mock"
    settings.memory.agentic_recall = True
    settings.memory.recall_min_score = 0.4
    settings.session.agentic_restore = True
    settings.session.restore_recall_count = 6
    return settings


async def _seed_workflow_session(
    store: RelationalStore,
    repo_path: Path,
) -> uuid.UUID:
    workflow = await store.create_workflow(
        id=uuid.uuid4(),
        name="tdd",
        version=3,
        enforcement="strict",
        steps=[{"name": "Test Writing"}, {"name": "Implementation"}],
        policies={"block_step_skips": True},
        default_for_repo=True,
    )
    repo = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="session-graph-repo",
        repo_url="https://example.com/session-graph",
        default_branch="main",
        workflow_id=workflow.id,
        state_path=str(repo_path / ".minder"),
        context_snapshot={},
        relationships={},
    )
    session = await store.create_session(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        repo_id=repo.id,
        project_context={
            "repo_path": str(repo_path),
            "branch": "feature/auth-v2",
            "open_files": ["src/minder/tools/session.py"],
        },
        active_skills={"testing": True},
        state={
            "task": "Fix JWT refresh token expiry",
            "next_steps": ["Confirm failing tests", "Patch refresh logic"],
        },
        ttl=3600,
    )
    await store.create_workflow_state(
        id=uuid.uuid4(),
        repo_id=repo.id,
        session_id=session.id,
        current_step="Implementation",
        completed_steps=["Test Writing"],
        blocked_by=[],
        artifacts={"failing_tests": "captured"},
        next_step="Verification",
    )
    return session.id


def test_build_targeted_queries_uses_task_step_and_branch() -> None:
    queries = SessionContextGraph.build_targeted_queries(
        session_state={"task": "Fix JWT refresh token expiry"},
        workflow_step="Implementation",
        project_context={"branch": "feature/auth-v2"},
    )

    assert queries[0] == "Fix JWT refresh token expiry Implementation"
    assert "best practices for Implementation phase" in queries
    assert "artifacts required in Implementation" in queries
    assert len(queries) == 3


@pytest.mark.asyncio
async def test_agentic_session_restore_adds_memories_and_coherence_warnings(
    store: RelationalStore,
    config: MinderConfig,
    tmp_path: Path,
) -> None:
    session_id = await _seed_workflow_session(store, tmp_path / "repo")
    memory_tools = MemoryTools(store, config)
    session_tools = SessionTools(store, config=config, memory_tools=memory_tools)
    await memory_tools.minder_memory_store(
        title="JWT refresh fix",
        content="Fix JWT refresh token expiry in feature/auth-v2 during implementation.",
        tags=["jwt", "implementation", "auth"],
        language="markdown",
    )
    await memory_tools.minder_memory_store(
        title="Old auth v1 design note",
        content="feature/auth-v1 used cookie sessions during design review.",
        tags=["design", "cookie"],
        language="markdown",
    )

    restored = await session_tools.minder_session_restore(session_id)

    assert restored["workflow_step"] == "Implementation"
    assert restored["continuity_packet"]["instruction_envelope"]["current_step"] == "Implementation"
    assert restored["relevant_memories"]
    assert restored["relevant_memories"][0]["title"] == "JWT refresh fix"
    assert any("stale_memory:" in item or "auth-v1" in item for item in restored["coherence_warnings"])
    assert restored["context_confidence"] < 1.0
