from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.server import build_transport
from minder.store.relational import RelationalStore
from minder.store.repo_state import RepoStateStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


def _load_module(path: Path, module_name: str):  # noqa: ANN001, ANN201
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    settings = MinderConfig()
    settings.server.transport = "sse"
    settings.verification.sandbox = "subprocess"
    return settings


@pytest.mark.asyncio
async def test_phase1_gate(
    tmp_path: Path,
    store: RelationalStore,
    config: MinderConfig,
) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "adder.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    user = await store.create_user(
        id=uuid.uuid4(),
        email="phase1-gate@example.com",
        username="phase1-gate",
        display_name="Phase 1 Gate",
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
        repo_name="phase1-gate-repo",
        repo_url="https://example.com/phase1-gate",
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

    auth_service = AuthService(store, config)
    created_user, api_key = await auth_service.register_user(
        email="login-gate@example.com",
        username="login-gate",
        display_name="Login Gate",
    )
    token = auth_service.issue_jwt(created_user)
    authorization = f"Bearer {token}"

    transport = build_transport(config=config, store=store)
    assert transport.transport_name == "sse"
    assert "minder_query" in transport.list_tools()

    # 1. Server starts with SSE transport.
    assert config.server.transport == "sse"

    # 2. Admin user is created via script.
    create_admin = _load_module(Path("scripts/create_admin.py"), "phase1_create_admin")
    created_admin = await create_admin.ensure_admin(
        store,
        config,
        email="admin-phase1@example.com",
        username="admin-phase1",
        display_name="Admin Phase 1",
    )
    existing_admin = await create_admin.ensure_admin(
        store,
        config,
        email="admin-phase1@example.com",
        username="admin-phase1",
        display_name="Admin Phase 1",
    )
    assert created_admin["created"] is True
    assert existing_admin["created"] is False

    # 3. Client connects via SSE, authenticates, receives JWT.
    login_result = await transport.call_tool(
        "minder_auth_login",
        arguments={"api_key": api_key},
    )
    assert login_result["token"]
    whoami = await transport.call_tool(
        "minder_auth_whoami",
        authorization=f"Bearer {login_result['token']}",
    )
    assert whoami["email"] == "login-gate@example.com"

    # 4. Workflow tools report current step and next step.
    workflow_info = await transport.call_tool(
        "minder_workflow_get",
        arguments={"repo_id": str(repo.id), "repo_path": str(repo_path)},
        authorization=authorization,
    )
    assert workflow_info["workflow"]["name"] == "tdd"
    workflow_step = await transport.call_tool(
        "minder_workflow_step",
        arguments={"repo_id": str(repo.id), "repo_path": str(repo_path)},
        authorization=authorization,
    )
    assert workflow_step["current_step"] == "Test Writing"
    assert workflow_step["next_step"] == "Implementation"

    # 5. Memory store -> semantic search -> recall works.
    memory_entry = await transport.call_tool(
        "minder_memory_store",
        arguments={
            "title": "Phase 1 TDD",
            "content": "Write tests before implementation",
            "tags": ["phase1", "tdd"],
            "language": "markdown",
        },
        authorization=authorization,
    )
    assert memory_entry["title"] == "Phase 1 TDD"
    recalled = await transport.call_tool(
        "minder_memory_recall",
        arguments={"query": "tests before implementation", "limit": 3},
        authorization=authorization,
    )
    assert recalled
    searched = await transport.call_tool(
        "minder_search",
        arguments={"query": "implementation", "limit": 3},
        authorization=authorization,
    )
    assert searched

    # 6. Repository-local `.minder/` state writes and restores.
    updated = await transport.call_tool(
        "minder_workflow_update",
        arguments={
            "repo_id": str(repo.id),
            "repo_path": str(repo_path),
            "completed_step": "Test Writing",
            "artifact_name": "tests.txt",
            "artifact_content": "added tests",
        },
        authorization=authorization,
    )
    assert updated["current_step"] == "Implementation"
    repo_state = await RepoStateStore(config.workflow.repo_state_dir).read_all(str(repo_path))
    assert repo_state["workflow"]["current_step"] == "Implementation"
    assert repo_state["artifacts"]["tests.txt"] == "added tests"

    # Session tool surface is also registered and callable.
    saved = await transport.call_tool(
        "minder_session_save",
        arguments={
            "session_id": str(session.id),
            "state": {"checkpoint": "phase1-gate"},
            "active_skills": {"phase": "gate"},
        },
        authorization=authorization,
    )
    assert saved["state"]["checkpoint"] == "phase1-gate"

    # Query/search flow is exposed through the transport.
    query_result = await transport.call_tool(
        "minder_query",
        arguments={
            "query": "explain add",
            "repo_path": str(repo_path),
            "session_id": str(session.id),
            "repo_id": str(repo.id),
            "workflow_name": "tdd",
        },
        authorization=authorization,
    )
    assert query_result["answer"]

    # 7. CI pipeline contract exists in GitHub Actions.
    ci_content = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "uv run pytest" in ci_content
    assert "uv run mypy src" in ci_content
