from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.observability.metrics import get_metrics_summary
from minder.store.relational import RelationalStore
from minder.store.repo_state import RepoStateStore
from minder.tools.auth import AuthTools
from minder.tools.memory import MemoryTools
from minder.tools.search import SearchTools
from minder.tools.session import SessionTools
from minder.tools.skills import SkillTools
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


@pytest.fixture
def auth_service(store: RelationalStore, config: MinderConfig) -> AuthService:
    return AuthService(store, config)


async def _seed_context(
    store: RelationalStore, repo_path: Path
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    user = await store.create_user(
        id=uuid.uuid4(),
        email="phase1@example.com",
        username="phase1",
        display_name="Phase 1",
        api_key_hash="hash",
        role="admin",
        is_active=True,
        settings={},
    )
    workflow = await store.create_workflow(
        id=uuid.uuid4(),
        name="tdd",
        version=1,
        steps=[{"name": "Test Writing"}, {"name": "Implementation"}],
        policies={"block_step_skips": True},
        default_for_repo=True,
    )
    repo = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="phase1-repo",
        repo_url="https://example.com/phase1",
        default_branch="main",
        workflow_id=workflow.id,
        state_path=str(repo_path / ".minder"),
        context_snapshot={},
        relationships={"service": ["tests"]},
    )
    session = await store.create_session(
        id=uuid.uuid4(),
        user_id=user.id,
        repo_id=repo.id,
        project_context={"repo_path": str(repo_path)},
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
        next_step="Implementation",
    )
    return user.id, workflow.id, repo.id, session.id


@pytest.mark.asyncio
async def test_repo_state_store_round_trip(
    repo_state_store: RepoStateStore, tmp_path: Path
) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    await repo_state_store.write_workflow_state(
        str(repo_path),
        {"current_step": "Test Writing", "completed_steps": []},
    )
    await repo_state_store.write_context(
        str(repo_path),
        {"open_files": ["src/app.py"]},
    )
    await repo_state_store.write_relationships(
        str(repo_path),
        {"service": ["tests"]},
    )
    await repo_state_store.write_artifact(
        str(repo_path),
        "note.txt",
        "phase1",
    )

    state = await repo_state_store.read_all(str(repo_path))
    assert state["workflow"]["current_step"] == "Test Writing"
    assert state["context"]["open_files"] == ["src/app.py"]
    assert state["relationships"]["service"] == ["tests"]
    assert "note.txt" in state["artifacts"]


def _init_git_repo(repo_path: Path, message: str) -> None:
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
        ["git", "commit", "-m", message],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )


@pytest.mark.asyncio
async def test_phase1_tool_modules_round_trip(
    store: RelationalStore,
    config: MinderConfig,
    auth_service: AuthService,
    repo_state_store: RepoStateStore,
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    user_id, workflow_id, repo_id, session_id = await _seed_context(store, repo_path)

    auth_tools = AuthTools(store, auth_service)
    session_tools = SessionTools(store)
    workflow_tools = WorkflowTools(store, repo_state_store)
    memory_tools = MemoryTools(store, config)
    skill_tools = SkillTools(store, config)
    search_tools = SearchTools(store, config)

    created_user, api_key = await auth_service.register_user(
        email="login@example.com",
        username="login",
        display_name="Login User",
    )
    login_result = await auth_tools.minder_auth_login(api_key)
    assert login_result["token"]

    whoami = await auth_tools.minder_auth_whoami(login_result["token"])
    assert whoami["email"] == "login@example.com"

    managed = await auth_tools.minder_auth_manage(
        actor_user_id=user_id,
        action="list_users",
    )
    assert any(item["email"] == "phase1@example.com" for item in managed["users"])

    session_context = await session_tools.minder_session_context(
        session_id,
        branch="main",
        open_files=["src/minder/tools/workflow.py"],
    )
    assert session_context["branch"] == "main"

    saved = await session_tools.minder_session_save(
        session_id,
        state={"checkpoint": "wave2"},
        active_skills={"phase": "wave2"},
    )
    assert saved["state"]["checkpoint"] == "wave2"

    restored = await session_tools.minder_session_restore(session_id)
    assert restored["state"]["checkpoint"] == "wave2"
    assert (
        restored["continuity_packet"]["instruction_envelope"]["current_step"]
        == "Test Writing"
    )
    assert "next_valid_actions" in restored["continuity_packet"]["session_brief"]

    workflow = await workflow_tools.minder_workflow_get(
        repo_id=repo_id, repo_path=str(repo_path)
    )
    assert workflow["workflow"]["name"] == "tdd"

    step = await workflow_tools.minder_workflow_step(
        repo_id=repo_id, repo_path=str(repo_path)
    )
    assert step["current_step"] == "Test Writing"

    guard = await workflow_tools.minder_workflow_guard(
        repo_id=repo_id,
        requested_step="Implementation",
    )
    assert guard["allowed"] is False
    assert guard["instruction_envelope"]["current_step"] == "Test Writing"
    assert "workflow_blocked" not in guard["violations"]

    updated = await workflow_tools.minder_workflow_update(
        repo_id=repo_id,
        repo_path=str(repo_path),
        completed_step="Test Writing",
        artifact_name="tests.txt",
        artifact_content="added tests",
    )
    assert updated["current_step"] == "Implementation"

    memory_entry = await memory_tools.minder_memory_store(
        title="TDD note",
        content="Write tests before implementation",
        tags=["tdd", "phase1"],
        language="markdown",
    )
    assert memory_entry["title"] == "TDD note"

    recalled = await memory_tools.minder_memory_recall(
        "tests before implementation",
        current_step="Test Writing",
        artifact_type="test_plan",
    )
    assert recalled
    assert recalled[0]["title"] == "TDD note"
    assert recalled[0]["step_compatibility"] > 0

    listed = await memory_tools.minder_memory_list()
    assert listed

    duplicate_memory = await memory_tools.minder_memory_store(
        title="TDD note duplicate",
        content="Write tests before implementation",
        tags=["tdd", "phase1", "duplicate"],
        language="markdown",
    )

    compaction_plan = await memory_tools.minder_memory_compact(
        memory_ids=[memory_entry["id"], duplicate_memory["id"]],
        similarity_threshold=0.9,
        dry_run=True,
    )
    assert compaction_plan["dry_run"] is True
    assert compaction_plan["duplicate_group_count"] == 1
    primary_id = str(compaction_plan["plans"][0]["primary_id"])
    duplicate_ids = {str(item) for item in compaction_plan["plans"][0]["duplicate_ids"]}

    compacted = await memory_tools.minder_memory_compact(
        memory_ids=[memory_entry["id"], duplicate_memory["id"]],
        similarity_threshold=0.9,
        dry_run=False,
    )
    assert compacted["compacted_count"] == 1
    assert compacted["deleted_count"] == 1

    post_compaction = await memory_tools.minder_memory_list()
    assert any(item["id"] == primary_id for item in post_compaction)
    assert not any(item["id"] in duplicate_ids for item in post_compaction)

    stored_skill = await skill_tools.minder_skill_store(
        title="Testing workflow skill",
        content="Capture failing tests and only then move into implementation.",
        language="python",
        tags=["tdd"],
        workflow_steps=["Test Writing"],
        artifact_types=["test_plan"],
        provenance="phase_4_4",
        quality_score=0.9,
    )
    assert stored_skill["provenance"] == "phase_4_4"

    recalled_skills = await skill_tools.minder_skill_recall(
        "write failing tests",
        current_step="Test Writing",
        artifact_type="test_plan",
    )
    assert recalled_skills
    assert recalled_skills[0]["title"] == "Testing workflow skill"
    assert recalled_skills[0]["step_compatibility"] > 0

    updated_skill = await skill_tools.minder_skill_update(
        stored_skill["id"],
        quality_score=1.0,
        tags=["tdd", "regression"],
        workflow_steps=["Test Writing"],
        artifact_types=["test_plan"],
        provenance="phase_4_4",
    )
    assert updated_skill["quality_score"] == 1.0

    listed_skills = await skill_tools.minder_skill_list(current_step="Test Writing")
    assert any(item["id"] == stored_skill["id"] for item in listed_skills)

    search_result = await search_tools.minder_search("implementation")
    assert search_result

    metrics_summary = await get_metrics_summary(store=store)
    assert metrics_summary["continuity_quality"]["packets_emitted_total"] >= 2
    assert metrics_summary["continuity_quality"]["recalls_total"] >= 1
    assert metrics_summary["continuity_quality"]["average_step_compatibility"] > 0

    deleted = await memory_tools.minder_memory_delete(memory_entry["id"])
    assert deleted["deleted"] is True
    deleted_skill = await skill_tools.minder_skill_delete(stored_skill["id"])
    assert deleted_skill["deleted"] is True

    repo_state = await repo_state_store.read_all(str(repo_path))
    assert repo_state["workflow"]["current_step"] == "Implementation"
    assert "tests.txt" in repo_state["artifacts"]
    assert repo_state["relationships"]["service"] == ["tests"]
    assert workflow_id
    assert created_user.id


@pytest.mark.asyncio
async def test_skill_import_git_round_trip(
    store: RelationalStore,
    config: MinderConfig,
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "skill-pack"
    repo_path.mkdir()
    skills_dir = repo_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "testing.md").write_text(
        "# Testing Guide\n\nWrite failing tests first.",
        encoding="utf-8",
    )
    (skills_dir / "catalog.json").write_text(
        """
        [
          {
            "title": "Release Checklist",
            "content": "Verify rollback and release notes before deploy.",
            "language": "markdown",
            "tags": ["release"],
            "workflow_steps": ["Release"],
            "artifact_types": ["release_notes"],
            "provenance": "git_import",
            "quality_score": 0.8
          }
        ]
        """.strip(),
        encoding="utf-8",
    )
    _init_git_repo(repo_path, "add skill pack")

    skill_tools = SkillTools(store, config)
    imported = await skill_tools.minder_skill_import_git(
        repo_url=str(repo_path),
        source_path="skills",
    )

    assert imported["imported_count"] == 2
    assert imported["created_count"] == 2

    listed = await skill_tools.minder_skill_list()
    assert any(item["title"] == "Testing Guide" for item in listed)
    assert any(item["title"] == "Release Checklist" for item in listed)
    assert all(item["source"]["path"] == "skills" for item in listed)

    imported_again = await skill_tools.minder_skill_import_git(
        repo_url=str(repo_path),
        source_path="skills",
    )
    assert imported_again["updated_count"] == 2


@pytest.mark.asyncio
async def test_skill_import_git_auto_discovers_when_default_path_missing(
    store: RelationalStore,
    config: MinderConfig,
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "fallback-skill-pack"
    repo_path.mkdir()
    (repo_path / "docs" / "skill-packs").mkdir(parents=True)
    (repo_path / "docs" / "skill-packs" / "release.md").write_text(
        "# Release skill\n\nVerify rollback and release notes before deploy.",
        encoding="utf-8",
    )
    (repo_path / "team-skills.json").write_text(
        """
        {
          "skills": [
            {
              "title": "Testing Guide",
              "content": "Write failing tests before implementation.",
              "language": "markdown",
              "tags": ["testing"],
              "workflow_steps": ["Test Writing"],
              "artifact_types": ["test_plan"],
              "provenance": "git_import",
              "quality_score": 0.9
            }
          ]
        }
        """.strip(),
        encoding="utf-8",
    )
    _init_git_repo(repo_path, "add fallback skill pack")

    skill_tools = SkillTools(store, config)
    imported = await skill_tools.minder_skill_import_git(
        repo_url=str(repo_path),
        source_path="skills",
    )

    assert imported["imported_count"] == 2
    assert imported["created_count"] == 2
    assert set(imported["resolved_paths"]) == {"docs/skill-packs", "team-skills.json"}

    listed = await skill_tools.minder_skill_list()
    assert {item["title"] for item in listed} == {"Release skill", "Testing Guide"}
    assert {str(item["source"]["path"]) for item in listed} == {
        "docs/skill-packs",
        "team-skills.json",
    }


@pytest.mark.asyncio
async def test_skill_import_git_aggregates_multiple_skill_roots_in_default_mode(
    store: RelationalStore,
    config: MinderConfig,
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "multi-skill-pack"
    repo_path.mkdir()
    (repo_path / "skills").mkdir()
    (repo_path / "skill-packs").mkdir()
    (repo_path / "skills" / "testing.md").write_text(
        "# Testing Guide\n\nWrite failing tests before implementation.",
        encoding="utf-8",
    )
    (repo_path / "skill-packs" / "release.json").write_text(
        """
        [
          {
            "title": "Release Checklist",
            "content": "Verify rollback and release notes before deploy.",
            "language": "markdown",
            "tags": ["release"],
            "workflow_steps": ["Release"],
            "artifact_types": ["release_notes"],
            "provenance": "git_import",
            "quality_score": 0.8
          }
        ]
        """.strip(),
        encoding="utf-8",
    )
    _init_git_repo(repo_path, "add multiple skill roots")

    skill_tools = SkillTools(store, config)
    imported = await skill_tools.minder_skill_import_git(
        repo_url=str(repo_path),
        source_path="skills",
    )

    assert imported["imported_count"] == 2
    assert set(imported["resolved_paths"]) == {"skills", "skill-packs"}

    listed = await skill_tools.minder_skill_list()
    assert any(item["title"] == "Testing Guide" for item in listed)
    assert any(item["title"] == "Release Checklist" for item in listed)


@pytest.mark.asyncio
async def test_skill_import_git_supports_agents_skill_directory(
    store: RelationalStore,
    config: MinderConfig,
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "coder-style-skills"
    repo_path.mkdir()
    (repo_path / ".agents" / "skills").mkdir(parents=True)
    (repo_path / ".agents" / "skills" / "rust").mkdir(parents=True)
    (repo_path / ".agents" / "skills" / "rust" / "SKILL.md").write_text(
        "---\nname: rust\ndescription: Rust engineering\n---\n\n# Skill: Rust\n\nBuild safe Rust systems.",
        encoding="utf-8",
    )
    (repo_path / ".agents" / "skills" / "rust" / "rules").mkdir()
    (repo_path / ".agents" / "skills" / "rust" / "rules" / "ownership.md").write_text(
        "Prefer ownership and borrowing over cloning.",
        encoding="utf-8",
    )
    _init_git_repo(repo_path, "add hidden agents skills")

    skill_tools = SkillTools(store, config)
    imported = await skill_tools.minder_skill_import_git(
        repo_url=str(repo_path),
        source_path=".agents/skills",
    )

    assert imported["imported_count"] == 1
    assert imported["resolved_paths"] == [".agents/skills"]

    listed = await skill_tools.minder_skill_list()
    assert listed[0]["title"] == "Skill: Rust"
    assert listed[0]["source"]["path"] == ".agents/skills"
    assert (
        listed[0]["source"]["file_path"] == ".agents/skills/rust/SKILL.md"
        or listed[0]["source"]["file_path"] == "rust/SKILL.md"
    )
    assert "rules" in listed[0]["source"].get("auxiliary_paths", [])
    assert "rules/ownership.md" in listed[0]["source"].get("auxiliary_paths", [])


@pytest.mark.asyncio
async def test_skill_import_git_does_not_create_auxiliary_rule_documents_as_skills(
    store: RelationalStore,
    config: MinderConfig,
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "coder-style-aux"
    repo_path.mkdir()
    (repo_path / ".agents" / "skills" / "go" / "rules").mkdir(parents=True)
    (repo_path / ".agents" / "skills" / "go" / "SKILL.md").write_text(
        "# Go Skill\n\nShip clear Go services.",
        encoding="utf-8",
    )
    (repo_path / ".agents" / "skills" / "go" / "rules" / "errors.md").write_text(
        "Return explicit error values.",
        encoding="utf-8",
    )
    _init_git_repo(repo_path, "add canonical skill with aux docs")

    skill_tools = SkillTools(store, config)
    imported = await skill_tools.minder_skill_import_git(
        repo_url=str(repo_path),
        source_path=".agents/skills",
    )

    assert imported["imported_count"] == 1
    listed = await skill_tools.minder_skill_list()
    assert len(listed) == 1
    assert listed[0]["title"] == "Go Skill"
