from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
import subprocess
import uuid

import pytest

from minder.config import MinderConfig
from minder.graph.state import GraphState
from minder.store.relational import RelationalStore
from minder.tools.memory import MemoryTools
from minder.tools.query import QueryTools
from minder.tools.session import SessionTools
from minder.tools.skills import SkillTools

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


class _Phase5Graph:
    async def run(self, state: GraphState) -> GraphState:
        state.llm_output = {
            "text": "Phase 5 runtime answer.",
            "provider": "local",
            "model": "test-double",
            "runtime": "fake",
        }
        state.reasoning_output = {"sources": []}
        state.guard_result = {"passed": True}
        state.verification_result = {"passed": True}
        state.evaluation = {"score": 1.0}
        state.transition_log = [{"edge": "complete"}]
        state.metadata["edge"] = "complete"
        return state

    async def stream(
        self, state: GraphState
    ) -> AsyncGenerator[dict[str, object], None]:
        final_state = await self.run(state)
        yield {"type": "attempt", "attempt": 1}
        yield {"type": "chunk", "attempt": 1, "delta": "Phase 5 "}
        yield {"type": "chunk", "attempt": 1, "delta": "runtime answer."}
        yield {"type": "final", "state": final_state}


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    return MinderConfig()


@pytest.mark.asyncio
async def test_phase5_gate(
    store: RelationalStore,
    config: MinderConfig,
    tmp_path: Path,
) -> None:
    user = await store.create_user(
        id=uuid.uuid4(),
        email="phase5@example.com",
        username="phase5",
        display_name="Phase 5",
        api_key_hash="hash",
        role="admin",
        is_active=True,
        settings={},
    )

    memory_tools = MemoryTools(store, config)
    skill_tools = SkillTools(store, config)
    session_tools = SessionTools(store)
    query_tools = QueryTools(store, config, graph=_Phase5Graph())

    primary_memory = await memory_tools.minder_memory_store(
        title="Phase 5 runtime note",
        content="Stream answers and keep repository scope optional.",
        tags=["phase5", "runtime"],
        language="markdown",
    )
    duplicate_memory = await memory_tools.minder_memory_store(
        title="Phase 5 runtime note duplicate",
        content="Stream answers and keep repository scope optional.",
        tags=["phase5", "runtime", "duplicate"],
        language="markdown",
    )
    compacted = await memory_tools.minder_memory_compact(
        memory_ids=[primary_memory["id"], duplicate_memory["id"]],
        similarity_threshold=0.9,
        dry_run=False,
    )
    assert compacted["compacted_count"] == 1
    assert compacted["deleted_count"] == 1

    repo_path = tmp_path / "skill-pack"
    repo_path.mkdir()
    skills_dir = repo_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "phase5.md").write_text(
        "# Phase 5 Skill\n\nUse source metadata and curation fields.",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Tests"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add phase5 skill pack"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    imported = await skill_tools.minder_skill_import_git(
        repo_url=str(repo_path),
        source_path="skills",
    )
    assert imported["imported_count"] == 1
    listed_skills = await skill_tools.minder_skill_list()
    assert any(
        isinstance(item.get("source"), dict) and item["source"].get("path") == "skills"
        for item in listed_skills
    )

    expired_session = await session_tools.minder_session_create(
        user_id=user.id,
        name="phase5-expired",
    )
    expired_session_id = uuid.UUID(expired_session["session_id"])
    await store.create_history(
        session_id=expired_session_id,
        role="assistant",
        content="expired phase 5 history",
    )
    await store.update_session(
        expired_session_id,
        ttl=1,
        last_active=datetime(2020, 1, 1, tzinfo=UTC),
    )
    cleanup = await session_tools.minder_session_cleanup(user_id=user.id)
    assert cleanup == {"deleted_sessions": 1, "deleted_history": 1}

    query_result = await query_tools.minder_query(
        "What can Minder do without a repository scope?",
        repo_path=None,
        user_id=user.id,
    )
    assert query_result["answer"] == "Phase 5 runtime answer."
    assert query_result["edge"] == "complete"

    stream_events = [
        event
        async for event in query_tools.minder_query_stream(
            "Stream the answer",
            repo_path=None,
            user_id=user.id,
        )
    ]
    assert [event["type"] for event in stream_events] == [
        "attempt",
        "chunk",
        "chunk",
        "final",
    ]
    assert stream_events[-1]["payload"]["answer"] == "Phase 5 runtime answer."
