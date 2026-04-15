from __future__ import annotations

import importlib.util
import subprocess
import uuid
from pathlib import Path

import pytest

from minder.config import MinderConfig
from minder.server import build_transport, build_vector_store
from minder.store.relational import RelationalStore

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
    return MinderConfig()


@pytest.mark.asyncio
async def test_create_admin_script_is_idempotent(store: RelationalStore, config: MinderConfig) -> None:
    module = _load_module(Path("scripts/create_admin.py"), "create_admin_script")
    first = await module.ensure_admin(
        store,
        config,
        email="admin@example.com",
        username="admin",
        display_name="Admin",
    )
    second = await module.ensure_admin(
        store,
        config,
        email="admin@example.com",
        username="admin",
        display_name="Admin",
    )

    assert first["created"] is True
    assert first["api_key"].startswith("mk_")
    assert second["created"] is False
    assert second["api_key"] is None


@pytest.mark.asyncio
async def test_seed_skills_script_imports_local_skill_directory(
    store: RelationalStore, config: MinderConfig, tmp_path: Path
) -> None:
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    (skill_dir / "review.md").write_text("# Review\nReview carefully.\n", encoding="utf-8")
    (skill_dir / "debug.md").write_text("# Debug\nDebug carefully.\n", encoding="utf-8")

    module = _load_module(Path("scripts/seed_skills.py"), "seed_skills_script")
    seeded = await module.seed_skills(store, config, str(skill_dir))
    reseeded = await module.seed_skills(store, config, str(skill_dir))

    assert seeded["imported"] == 2
    assert reseeded["skipped"] >= 2


@pytest.mark.asyncio
async def test_seed_skills_script_git_clone_path(
    store: RelationalStore, config: MinderConfig, tmp_path: Path
) -> None:
    """Git-clone path: subprocess.run is called with git clone when the source
    is not a local path.  We monkeypatch the module's subprocess attribute to
    write synthetic skill files into the temp dir instead of hitting the network."""

    module = _load_module(Path("scripts/seed_skills.py"), "seed_skills_script_clone")

    def _fake_git_clone(
        cmd: list[str], *, check: bool, capture_output: bool, text: bool
    ) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
        """Simulate `git clone --depth 1 <url> <dest>` by writing files."""
        assert cmd[0] == "git"
        assert "clone" in cmd
        dest = Path(cmd[-1])
        (dest / "architecture.md").write_text(
            "# Architecture\nClean arch rules.\n", encoding="utf-8"
        )
        (dest / "testing.md").write_text(
            "# Testing\nWrite tests first.\n", encoding="utf-8"
        )
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    # Patch subprocess.run on the dynamically loaded module's own subprocess reference
    original_run = module.subprocess.run
    module.subprocess.run = _fake_git_clone  # type: ignore[method-assign]
    try:
        fake_repo_url = "https://github.com/example/skills-repo.git"
        seeded = await module.seed_skills(store, config, fake_repo_url)

        assert seeded["imported"] == 2
        assert seeded["skipped"] == 0

        # Second run: same URL, same titles → all skipped (idempotent)
        reseeded = await module.seed_skills(store, config, fake_repo_url)

        assert reseeded["imported"] == 0
        assert reseeded["skipped"] == 2
    finally:
        module.subprocess.run = original_run  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_server_build_transport_registers_expected_tools(
    store: RelationalStore, config: MinderConfig, tmp_path: Path
) -> None:
    user = await store.create_user(
        id=uuid.uuid4(),
        email="server@example.com",
        username="server",
        display_name="Server User",
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
        policies={},
        default_for_repo=True,
    )
    repo = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="server-repo",
        repo_url="https://example.com/server",
        default_branch="main",
        workflow_id=workflow.id,
        state_path=str(tmp_path / "repo" / ".minder"),
        context_snapshot={},
        relationships={},
    )
    await store.create_session(
        id=uuid.uuid4(),
        user_id=user.id,
        repo_id=repo.id,
        project_context={},
        active_skills={},
        state={},
        ttl=3600,
    )

    vector_store = build_vector_store(config=config, store=store)
    transport = build_transport(config=config, store=store, vector_store=vector_store)
    tool_names = transport.list_tools()

    assert "minder_auth_login" in tool_names
    assert "minder_session_create" in tool_names
    assert "minder_workflow_get" in tool_names
    assert "minder_query" in tool_names


def test_wave3_assets_exist_and_contain_expected_commands() -> None:
    compose = Path("docker/docker-compose.local.yml")
    ci_workflow = Path(".github/workflows/ci.yml")
    release_workflow = Path(".github/workflows/release.yml")
    download_script = Path("scripts/download_models.sh")

    assert compose.exists()
    compose_text = compose.read_text(encoding="utf-8")
    assert "mongodb:" in compose_text
    assert "redis:" in compose_text
    assert "milvus-standalone:" in compose_text
    assert "etcd:" in compose_text
    assert "minio:" in compose_text
    assert ci_workflow.exists()
    assert "make test" in ci_workflow.read_text(encoding="utf-8")
    assert release_workflow.exists()
    release_workflow_text = release_workflow.read_text(encoding="utf-8")
    assert "docker/Dockerfile.api" in release_workflow_text
    assert "docker/Dockerfile.dashboard" in release_workflow_text
    assert "install-minder-${{ needs.build-dist.outputs.release_tag }}.sh" in release_workflow_text
    assert "dist/release/docker-compose.yml" in release_workflow_text
    assert "dist/release/Caddyfile" in release_workflow_text
    assert "body_path: dist/release/release-notes.md" in release_workflow_text
    assert "cache-from: type=gha,scope=minder-api" in release_workflow_text
    assert "cache-to: type=gha,mode=max,scope=minder-api" in release_workflow_text
    assert download_script.exists()
    assert "curl -L" in download_script.read_text(encoding="utf-8")
