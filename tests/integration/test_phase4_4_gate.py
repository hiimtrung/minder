from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from minder.config import MinderConfig
from minder.graph.state import GraphState
from minder.observability.metrics import get_metrics_summary
from minder.store.relational import RelationalStore
from minder.store.repo_state import RepoStateStore
from minder.tools.memory import MemoryTools
from minder.tools.query import QueryTools
from minder.tools.session import SessionTools
from minder.tools.skills import SkillTools
from minder.tools.workflow import WorkflowTools

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


class _FakeGraph:
    async def run(self, state: GraphState) -> GraphState:
        state.llm_output = {
            "text": "Answer: continuity gate satisfied.",
            "provider": "local",
            "model": "test-double",
            "runtime": "fake",
        }
        state.reasoning_output = {"sources": [{"title": "continuity-source"}]}
        state.guard_result = {"passed": True}
        state.verification_result = {"passed": True}
        state.evaluation = {"score": 1.0}
        state.transition_log = [{"edge": "guard_failed"}, {"edge": "complete"}]
        state.metadata["edge"] = "complete"
        return state


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


async def _seed_phase4_4_context(
    store: RelationalStore,
    repo_path: Path,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    workflow = await store.create_workflow(
        id=uuid.uuid4(),
        name="phase-4-4",
        version=4,
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
        repo_name="phase4-4-repo",
        repo_url="https://example.com/phase4-4",
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
        project_context={"repo_path": str(repo_path), "branch": "main"},
        active_skills={"continuity": True},
        state={"task": "Close P4.4 backlog"},
        ttl=3600,
    )
    await store.create_workflow_state(
        id=uuid.uuid4(),
        repo_id=repo.id,
        session_id=session.id,
        current_step="Test Writing",
        completed_steps=["Problem Analysis"],
        blocked_by=[],
        artifacts={"test_plan": "outlined"},
        next_step="Implementation",
    )
    return repo.id, session.id, workflow.id


@pytest.mark.asyncio
async def test_phase4_4_continuity_gate(
    store: RelationalStore,
    config: MinderConfig,
    repo_state_store: RepoStateStore,
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "app.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")

    repo_id, session_id, workflow_id = await _seed_phase4_4_context(store, repo_path)
    del workflow_id

    session_tools = SessionTools(store)
    workflow_tools = WorkflowTools(store, repo_state_store)
    memory_tools = MemoryTools(store, config)
    skill_tools = SkillTools(store, config)
    query_tools = QueryTools(store, config, graph=_FakeGraph())

    restored = await session_tools.minder_session_restore(session_id)
    assert (
        restored["continuity_packet"]["instruction_envelope"]["current_step"]
        == "Test Writing"
    )

    guard = await workflow_tools.minder_workflow_guard(
        repo_id=repo_id,
        requested_step="Implementation",
        action="write implementation",
    )
    assert guard["allowed"] is False
    assert "instruction_envelope" in guard

    memory = await memory_tools.minder_memory_store(
        title="Phase 4.4 continuity memory",
        content="Keep failing tests and continuity packet aligned before implementation.",
        tags=["test_plan", "continuity"],
        language="markdown",
    )
    recalled_memory = await memory_tools.minder_memory_recall(
        "keep failing tests aligned",
        current_step="Test Writing",
        artifact_type="test_plan",
    )
    assert recalled_memory
    assert recalled_memory[0]["id"] == memory["id"]

    skill = await skill_tools.minder_skill_store(
        title="Phase 4.4 skill",
        content="Use continuity packets and prompt correction retries when the workflow contract fails.",
        language="python",
        workflow_steps=["Test Writing"],
        artifact_types=["test_plan"],
        provenance="phase_4_4_gate",
        quality_score=0.8,
    )
    recalled_skills = await skill_tools.minder_skill_recall(
        "workflow contract fails",
        current_step="Test Writing",
        artifact_type="test_plan",
    )
    assert recalled_skills
    assert recalled_skills[0]["id"] == skill["id"]

    query_result = await query_tools.minder_query(
        "explain the next safe step",
        repo_path=str(repo_path),
        repo_id=repo_id,
        session_id=session_id,
        workflow_name="phase-4-4",
    )
    assert query_result["answer"].startswith("Answer:")
    assert query_result["guard_result"]["passed"] is True

    summary = await get_metrics_summary(store=store)
    continuity = summary["continuity_quality"]
    assert continuity["packets_emitted_total"] >= 3
    assert continuity["recalls_total"] >= 1
    assert continuity["average_step_compatibility"] > 0
    assert continuity["average_skill_quality"] > 0
    assert continuity["query_prompts_by_source"]["builtin"] >= 1
    assert continuity["correction_retries_total"] >= 1
    assert continuity["gates_by_outcome"]["blocked"] >= 1
