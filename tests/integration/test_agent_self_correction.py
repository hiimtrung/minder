"""P8-VERIFY — acceptance gate for Phase 8: Agent Intelligence and Self-Correction.

Covers:
  P8-T01  minder_memory_update round-trip (update content, re-embed, audit log)
  P8-T02  Skill deprecated flag: create → deprecate → absent from recall/list
  P8-T03  minder_session_summarize: generates and persists structured summary
  P8-T04  tool_capability_manifest includes usage patterns
  P8-T05  ClarificationNode triggers on correction intent; skips on clarification_done
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from minder.config import MinderConfig
from minder.graph.nodes.clarification import ClarificationNode
from minder.graph.nodes.planning import PlanningNode
from minder.graph.state import GraphState
from minder.store.relational import RelationalStore
from minder.tools.memory import MemoryTools
from minder.tools.registry import TOOL_USAGE_PATTERNS, tool_capability_manifest
from minder.tools.session import SessionTools
from minder.tools.skills import SkillTools

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    return MinderConfig(
        embedding={"provider": "fastembed", "runtime": "mock"},
        llm={"provider": "litert", "litert_backend": "mock"},
    )


# ---------------------------------------------------------------------------
# P8-T01 — minder_memory_update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_update_changes_content(store: RelationalStore, config: MinderConfig) -> None:
    tools = MemoryTools(store, config)

    created = await tools.minder_memory_store(
        title="Auth strategy",
        content="Use JWT tokens for auth.",
        tags=["auth"],
        language="markdown",
    )
    memory_id = created["id"]

    updated = await tools.minder_memory_update(
        memory_id,
        content="Use OAuth2 with PKCE for auth.",
        tags=["auth", "oauth2"],
    )

    assert updated["updated"] is True
    assert updated["id"] == memory_id
    assert "oauth2" in [t.lower() for t in updated["tags"]]


@pytest.mark.asyncio
async def test_memory_update_rejects_unknown_id(store: RelationalStore, config: MinderConfig) -> None:
    tools = MemoryTools(store, config)
    with pytest.raises(ValueError, match="Memory not found"):
        await tools.minder_memory_update(str(uuid.uuid4()), title="x")


@pytest.mark.asyncio
async def test_memory_update_title_only(store: RelationalStore, config: MinderConfig) -> None:
    tools = MemoryTools(store, config)
    created = await tools.minder_memory_store(
        title="Old title", content="Some content", tags=[], language="markdown"
    )
    updated = await tools.minder_memory_update(created["id"], title="New title")
    assert updated["updated"] is True


# ---------------------------------------------------------------------------
# P8-T02 — Skill deprecated flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skill_deprecated_absent_from_recall(
    store: RelationalStore, config: MinderConfig
) -> None:
    tools = SkillTools(store, config)

    await tools.minder_skill_store(
        title="TDD cycle",
        content="Red-green-refactor cycle for test-driven development.",
        language="markdown",
        tags=["tdd", "testing"],
        quality_score=0.9,
        source_metadata={"origin": "test"},
    )

    results_before = await tools.minder_skill_recall("tdd cycle testing")
    assert any("TDD" in r["title"] for r in results_before), "Skill should appear before deprecation"

    skills = await tools.minder_skill_list()
    skill_id = next(s["id"] for s in skills if "TDD" in s["title"])

    await tools.minder_skill_update(skill_id, deprecated=True)

    results_after = await tools.minder_skill_recall("tdd cycle testing")
    assert not any(r["id"] == skill_id for r in results_after), "Deprecated skill must not appear in recall"


@pytest.mark.asyncio
async def test_skill_deprecated_absent_from_list(
    store: RelationalStore, config: MinderConfig
) -> None:
    tools = SkillTools(store, config)

    await tools.minder_skill_store(
        title="Old deploy script",
        content="Deploy using FTP.",
        language="markdown",
        tags=["deploy"],
        quality_score=0.3,
        source_metadata={"origin": "test"},
    )

    skills_before = await tools.minder_skill_list()
    assert any("Old deploy" in s["title"] for s in skills_before)

    skill_id = next(s["id"] for s in skills_before if "Old deploy" in s["title"])
    await tools.minder_skill_update(skill_id, deprecated=True)

    skills_after = await tools.minder_skill_list()
    assert not any(s["id"] == skill_id for s in skills_after)


@pytest.mark.asyncio
async def test_skill_serialize_includes_deprecated(
    store: RelationalStore, config: MinderConfig
) -> None:
    tools = SkillTools(store, config)
    created = await tools.minder_skill_store(
        title="Active skill", content="Content.", language="markdown", tags=[]
    )
    assert created.get("deprecated") is False

    updated = await tools.minder_skill_update(created["id"], deprecated=True)
    assert updated.get("deprecated") is True


# ---------------------------------------------------------------------------
# P8-T03 — minder_session_summarize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_summarize_returns_structured_summary(store: RelationalStore) -> None:
    session_tools = SessionTools(store)

    session = await session_tools.minder_session_create(
        user_id=uuid.uuid4(),
        name="test-project",
        project_context={"repo_path": "/tmp/repo", "branch": "main", "open_files": ["app.py"]},
    )
    session_id = uuid.UUID(session["session_id"])

    await session_tools.minder_session_save(
        session_id,
        state={
            "task": "Implement OAuth2 login",
            "next_steps": ["Add callback endpoint", "Test token exchange"],
            "blockers": [],
        },
    )

    result = await session_tools.minder_session_summarize(session_id)

    assert result["session_id"] == str(session_id)
    summary = result["summary"]
    assert "task" in summary
    assert "completed" in summary
    assert "blockers" in summary
    assert "next_actions" in summary


@pytest.mark.asyncio
async def test_session_summarize_persists_to_state(store: RelationalStore) -> None:
    session_tools = SessionTools(store)

    session = await session_tools.minder_session_create(
        user_id=uuid.uuid4(), name="persist-test"
    )
    session_id = uuid.UUID(session["session_id"])

    await session_tools.minder_session_summarize(session_id)

    restored = await session_tools.minder_session_restore(session_id)
    assert "summary" in restored["state"], "Summary must be persisted in session.state"


@pytest.mark.asyncio
async def test_session_summarize_rejects_unknown_session(store: RelationalStore) -> None:
    session_tools = SessionTools(store)
    with pytest.raises(ValueError):
        await session_tools.minder_session_summarize(uuid.uuid4())


# ---------------------------------------------------------------------------
# P8-T04 — Tool usage guidance in manifest
# ---------------------------------------------------------------------------


def test_tool_usage_patterns_non_empty() -> None:
    assert len(TOOL_USAGE_PATTERNS) >= 10
    assert "minder_memory_update" in TOOL_USAGE_PATTERNS
    assert "minder_session_summarize" in TOOL_USAGE_PATTERNS
    assert "minder_skill_update" in TOOL_USAGE_PATTERNS
    assert "minder_workflow_guard" in TOOL_USAGE_PATTERNS


def test_tool_capability_manifest_includes_patterns() -> None:
    manifest = tool_capability_manifest()
    assert "Usage guidance:" in manifest
    assert "minder_memory_update" in manifest
    assert "minder_session_summarize" in manifest
    assert "deprecated" in manifest


def test_tool_capability_manifest_includes_new_tools() -> None:
    manifest = tool_capability_manifest()
    assert "minder_memory_update" in manifest
    assert "minder_session_summarize" in manifest


# ---------------------------------------------------------------------------
# P8-T05 — ClarificationNode + PlanningNode correction intent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "fix memory về authentication",
        "update memory sai",
        "wrong memory cần sửa",
        "sửa memory cũ",
        "cập nhật skill không còn phù hợp",
        "deprecate skill này đi",
        "xóa memory",
    ],
)
def test_planning_detects_correction_intent(query: str) -> None:
    node = PlanningNode()
    state = GraphState(query=query)
    result = node.run(state)
    assert result.plan["intent"] == "correction", (
        f"Expected 'correction' intent for query '{query}', got '{result.plan['intent']}'"
    )


def test_planning_does_not_flag_normal_query_as_correction() -> None:
    node = PlanningNode()
    for query in ("implement login feature", "debug this error", "explain the auth flow"):
        state = GraphState(query=query)
        result = node.run(state)
        assert result.plan["intent"] != "correction", (
            f"Query '{query}' should NOT trigger correction intent"
        )


def test_clarification_node_triggers_on_correction_intent() -> None:
    node = ClarificationNode()
    state = GraphState(query="fix memory về authentication")
    state.plan = {"intent": "correction"}

    result = node.run(state)

    assert result.metadata.get("needs_clarification") is True
    options = result.metadata.get("clarification_options", [])
    assert len(options) == 3
    assert all("id" in o and "label" in o and "tool_hint" in o for o in options)
    assert result.llm_output.get("provider") == "clarification"
    assert len(result.llm_output.get("text", "")) > 0


def test_clarification_node_generates_memory_options_for_memory_query() -> None:
    node = ClarificationNode()
    state = GraphState(query="update memory sai về authentication")
    state.plan = {"intent": "correction"}

    result = node.run(state)

    option_ids = {o["id"] for o in result.metadata["clarification_options"]}
    assert "update_memory" in option_ids


def test_clarification_node_generates_skill_options_for_skill_query() -> None:
    node = ClarificationNode()
    state = GraphState(query="deprecate skill cũ không dùng nữa")
    state.plan = {"intent": "correction"}

    result = node.run(state)

    option_ids = {o["id"] for o in result.metadata["clarification_options"]}
    assert "deprecate_skill" in option_ids


def test_clarification_node_skips_when_already_confirmed() -> None:
    node = ClarificationNode()
    state = GraphState(query="fix skill cũ")
    state.plan = {"intent": "correction"}
    state.metadata["clarification_done"] = True

    result = node.run(state)

    assert not result.metadata.get("needs_clarification")
    assert result.llm_output == {}


def test_clarification_node_passthrough_on_non_correction_intent() -> None:
    node = ClarificationNode()
    state = GraphState(query="implement login")
    state.plan = {"intent": "code_gen"}

    result = node.run(state)

    assert not result.metadata.get("needs_clarification")
    assert result.llm_output == {}


# ---------------------------------------------------------------------------
# P8-T02 — Schema migration: deprecated column added to existing DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_migration_adds_deprecated_column() -> None:
    """Calling init_db() twice on an existing DB must not error and must have the column."""
    store = RelationalStore(IN_MEMORY_URL)
    await store.init_db()
    # Call again to simulate server restart on existing DB
    await store.init_db()

    skill = await store.create_skill(
        id=uuid.uuid4(),
        title="Test",
        content="Content",
        language="markdown",
        tags=[],
        embedding=None,
    )
    updated = await store.update_skill(skill.id, deprecated=True)
    assert updated is not None
    assert bool(getattr(updated, "deprecated", False)) is True
    await store.dispose()
