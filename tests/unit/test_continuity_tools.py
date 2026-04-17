from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from minder.config import MinderConfig
from minder.store.relational import RelationalStore
from minder.store.repo_state import RepoStateStore
from minder.tools.memory import MemoryTools
from minder.tools.session import SessionTools
from minder.tools.workflow import WorkflowTools

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    return MinderConfig()


@pytest.fixture
def repo_state_store(config: MinderConfig) -> RepoStateStore:
    return RepoStateStore(config.workflow.repo_state_dir)


async def _seed_workflow_session(
    store: RelationalStore,
    repo_path: Path,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    workflow = await store.create_workflow(
        id=uuid.uuid4(),
        name="tdd",
        version=3,
        enforcement="strict",
        steps=[
            {"name": "Problem Analysis"},
            {"name": "Test Writing"},
            {"name": "Implementation"},
        ],
        policies={"block_step_skips": True},
        default_for_repo=True,
    )
    repo = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="continuity-repo",
        repo_url="https://example.com/continuity",
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
            "branch": "feature/continuity",
            "open_files": ["src/minder/tools/session.py"],
        },
        active_skills={"testing": True},
        state={
            "task": "Finish continuity packet",
            "next_steps": ["Write session synthesis", "Enforce workflow envelope"],
        },
        ttl=3600,
    )
    await store.create_workflow_state(
        id=uuid.uuid4(),
        repo_id=repo.id,
        session_id=session.id,
        current_step="Test Writing",
        completed_steps=["Problem Analysis"],
        blocked_by=[],
        artifacts={"test_plan": "drafted"},
        next_step="Implementation",
    )
    return repo.id, session.id, workflow.id


@pytest.mark.asyncio
async def test_session_restore_includes_continuity_packet(
    store: RelationalStore,
    tmp_path: Path,
) -> None:
    repo_id, session_id, workflow_id = await _seed_workflow_session(
        store, tmp_path / "repo"
    )
    del repo_id, workflow_id
    tools = SessionTools(store)

    restored = await tools.minder_session_restore(session_id)

    packet = restored["continuity_packet"]
    assert packet["instruction_envelope"]["current_step"] == "Test Writing"
    assert packet["instruction_envelope"]["workflow_version"] == 3
    assert (
        packet["session_brief"]["problem_framing"]["task"] == "Finish continuity packet"
    )


@pytest.mark.asyncio
async def test_workflow_guard_reports_envelope_and_violations(
    store: RelationalStore,
    repo_state_store: RepoStateStore,
    tmp_path: Path,
) -> None:
    repo_id, session_id, workflow_id = await _seed_workflow_session(
        store, tmp_path / "repo"
    )
    del session_id, workflow_id
    tools = WorkflowTools(store, repo_state_store)

    guarded = await tools.minder_workflow_guard(
        repo_id=repo_id,
        requested_step="Implementation",
        action="write implementation",
    )

    assert guarded["allowed"] is False
    assert "action_outside_current_step" in guarded["violations"]
    assert guarded["instruction_envelope"]["required_artifacts"] == [
        "test_plan",
        "failing_tests",
    ]


@pytest.mark.asyncio
async def test_memory_recall_prioritizes_step_compatibility(
    store: RelationalStore,
    config: MinderConfig,
) -> None:
    tools = MemoryTools(store, config)
    await tools.minder_memory_store(
        title="Test plan drafting",
        content="Write failing tests before implementation and record the test plan.",
        tags=["test", "test_plan"],
        language="markdown",
    )
    await tools.minder_memory_store(
        title="Release checklist",
        content="Prepare release notes and rollback plan.",
        tags=["release"],
        language="markdown",
    )

    recalled = await tools.minder_memory_recall(
        "write tests before implementation",
        current_step="Test Writing",
        artifact_type="test_plan",
    )

    assert recalled[0]["title"] == "Test plan drafting"
    assert recalled[0]["step_compatibility"] > recalled[1]["step_compatibility"]
    assert "Top recalled memories" in recalled[0]["recall_summary"]
    assert recalled[0]["synthesis"]["provider"] in {"heuristic", "local_llm"}
