"""Integration tests for P4-T07 — user, workflow, and repository admin API endpoints.

These tests use an in-memory SQLite store (same pattern as the existing
test_phase4_http_admin.py) to validate the new HTTP routes end-to-end
without requiring a running Minder server.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from starlette.testclient import TestClient

from minder.auth.service import AuthService, UserRole
from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
from minder.presentation.http.admin.routes import build_http_app
from minder.store.relational import RelationalStore
from minder.store.graph import KnowledgeGraphStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    return MinderConfig()


@pytest.fixture
def cache() -> LRUCacheProvider:
    return LRUCacheProvider()


@pytest.fixture
def graph_store_db_url(tmp_path) -> str:  # noqa: ANN001
    return f"sqlite+aiosqlite:///{tmp_path / 'graph.db'}"


@pytest_asyncio.fixture
async def graph_store(graph_store_db_url: str) -> KnowledgeGraphStore:
    backend = KnowledgeGraphStore(graph_store_db_url)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def app(
    store: RelationalStore,
    graph_store: KnowledgeGraphStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
) -> Any:
    return build_http_app(config=config, store=store, graph_store=graph_store, cache=cache)


@pytest_asyncio.fixture
async def admin_client(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    app: Any,
) -> TestClient:
    """Return a TestClient with an active admin session cookie."""
    auth = AuthService(store=store, config=config, cache=cache)
    admin, api_key = await auth.register_user(
        email="expansion-admin@example.com",
        username="expansion_admin",
        display_name="Expansion Admin",
        role=UserRole.ADMIN,
    )
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.post("/v1/admin/login", json={"api_key": api_key})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return client


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_list_users(admin_client: TestClient) -> None:
    resp = admin_client.get("/v1/admin/users")
    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    assert isinstance(data["users"], list)
    assert len(data["users"]) >= 1
    # All returned users have required fields
    for u in data["users"]:
        for field in ("id", "username", "email", "role", "is_active"):
            assert field in u, f"Missing field {field!r} in user payload"


@pytest.mark.asyncio
async def test_admin_can_create_user(admin_client: TestClient) -> None:
    resp = admin_client.post(
        "/v1/admin/users",
        json={
            "username": "created_admin",
            "email": "created-admin@example.com",
            "display_name": "Created Admin",
            "role": "admin",
            "password": "secret-pass",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user"]["username"] == "created_admin"
    assert data["user"]["role"] == "admin"
    assert data["api_key"].startswith("mk_")


@pytest.mark.asyncio
async def test_admin_can_get_user_detail(
    admin_client: TestClient,
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
) -> None:
    auth = AuthService(store=store, config=config, cache=cache)
    user, _ = await auth.register_user(
        email="detail-user@example.com",
        username="detail_user",
        display_name="Detail User",
    )
    resp = admin_client.get(f"/v1/admin/users/{user.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["username"] == "detail_user"
    assert data["user"]["email"] == "detail-user@example.com"


@pytest.mark.asyncio
async def test_admin_can_update_user_display_name(
    admin_client: TestClient,
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
) -> None:
    auth = AuthService(store=store, config=config, cache=cache)
    user, _ = await auth.register_user(
        email="patch-user@example.com",
        username="patch_user",
        display_name="Original Name",
    )
    resp = admin_client.patch(
        f"/v1/admin/users/{user.id}",
        json={"display_name": "Updated Name"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["display_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_admin_can_deactivate_user(
    admin_client: TestClient,
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
) -> None:
    auth = AuthService(store=store, config=config, cache=cache)
    user, _ = await auth.register_user(
        email="deactivate-user@example.com",
        username="deactivate_user",
        display_name="To Be Deactivated",
    )
    resp = admin_client.delete(f"/v1/admin/users/{user.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["is_active"] is False


@pytest.mark.asyncio
async def test_user_detail_404_for_unknown_id(admin_client: TestClient) -> None:
    resp = admin_client.get(f"/v1/admin/users/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_user_endpoints_require_auth(app: Any) -> None:
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/v1/admin/users")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Workflow management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_list_workflows_empty(admin_client: TestClient) -> None:
    resp = admin_client.get("/v1/admin/workflows")
    assert resp.status_code == 200
    data = resp.json()
    assert "workflows" in data
    assert isinstance(data["workflows"], list)


@pytest.mark.asyncio
async def test_admin_can_create_workflow(admin_client: TestClient) -> None:
    payload = {
        "name": "tdd",
        "description": "Test-driven development workflow",
        "enforcement": "strict",
        "steps": [
            {"name": "write_test", "description": "Write a failing test", "gate": None},
            {"name": "implement", "description": "Make the test pass", "gate": None},
            {"name": "refactor", "description": "Clean up", "gate": None},
        ],
    }
    resp = admin_client.post("/v1/admin/workflows", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["workflow"]["name"] == "tdd"
    assert data["workflow"]["enforcement"] == "strict"
    assert len(data["workflow"]["steps"]) == 3
    assert "id" in data["workflow"]


@pytest.mark.asyncio
async def test_admin_can_get_workflow_detail(admin_client: TestClient) -> None:
    create_resp = admin_client.post(
        "/v1/admin/workflows",
        json={"name": "review-flow", "description": "Code review flow"},
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["workflow"]["id"]

    detail_resp = admin_client.get(f"/v1/admin/workflows/{workflow_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["workflow"]["name"] == "review-flow"


@pytest.mark.asyncio
async def test_admin_can_update_workflow(admin_client: TestClient) -> None:
    create_resp = admin_client.post(
        "/v1/admin/workflows",
        json={"name": "update-target", "enforcement": "strict"},
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["workflow"]["id"]

    patch_resp = admin_client.patch(
        f"/v1/admin/workflows/{workflow_id}",
        json={"enforcement": "advisory", "description": "Patched"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["workflow"]["enforcement"] == "advisory"
    assert data["workflow"]["description"] == "Patched"


@pytest.mark.asyncio
async def test_admin_can_delete_workflow(admin_client: TestClient) -> None:
    create_resp = admin_client.post(
        "/v1/admin/workflows",
        json={"name": "to-delete"},
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["workflow"]["id"]

    del_resp = admin_client.delete(f"/v1/admin/workflows/{workflow_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    # Confirm it's gone
    get_resp = admin_client.get(f"/v1/admin/workflows/{workflow_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_workflow_create_requires_name(admin_client: TestClient) -> None:
    resp = admin_client.post("/v1/admin/workflows", json={"description": "no name"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_workflow_endpoints_require_auth(app: Any) -> None:
    client = TestClient(app, raise_server_exceptions=True)
    assert client.get("/v1/admin/workflows").status_code in (401, 403)
    assert client.post("/v1/admin/workflows", json={"name": "x"}).status_code in (401, 403)


# ---------------------------------------------------------------------------
# Repository management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_list_repositories_empty(admin_client: TestClient) -> None:
    resp = admin_client.get("/v1/admin/repositories")
    assert resp.status_code == 200
    data = resp.json()
    assert "repositories" in data
    assert isinstance(data["repositories"], list)


@pytest.mark.asyncio
async def test_repositories_endpoint_requires_auth(app: Any) -> None:
    client = TestClient(app, raise_server_exceptions=True)
    assert client.get("/v1/admin/repositories").status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_can_sync_repository_graph(
    admin_client: TestClient,
    store: RelationalStore,
    graph_store: KnowledgeGraphStore,
) -> None:
    repository = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="sync-target",
        repo_url="https://example.com/sync-target",
        default_branch="main",
        state_path="/workspace/sync-target/.minder",
        context_snapshot={},
        relationships={},
    )

    response = admin_client.post(
        f"/v1/admin/repositories/{repository.id}/graph-sync",
        json={
            "payload_version": "2026-04-15",
            "source": "minder-cli",
            "repo_path": "/workspace/sync-target",
            "branch": "feature/fast-sync",
            "diff_base": "origin/main",
            "sync_metadata": {"trigger": "manual-test"},
            "nodes": [
                {
                    "node_type": "file",
                    "name": "src/app.py",
                    "metadata": {"language": "python"},
                },
                {
                    "node_type": "function",
                    "name": "src/app.py::build_app",
                    "metadata": {"signature": "build_app() -> App"},
                },
            ],
            "edges": [
                {
                    "source": {"node_type": "file", "name": "src/app.py"},
                    "target": {"node_type": "function", "name": "src/app.py::build_app"},
                    "relation": "contains",
                    "weight": 1.0,
                }
            ],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["repo_id"] == str(repository.id)
    assert payload["repository_name"] == "sync-target"
    assert payload["nodes_upserted"] == 2
    assert payload["edges_upserted"] == 1

    file_node = await graph_store.get_node_by_name("file", "src/app.py")
    function_node = await graph_store.get_node_by_name("function", "src/app.py::build_app")
    assert file_node is not None
    assert function_node is not None
    assert file_node.node_metadata["repo_id"] == str(repository.id)
    assert file_node.node_metadata["branch"] == "feature/fast-sync"

    neighbors = await graph_store.get_neighbors(file_node.id, direction="out", relation="contains")
    neighbor_names = {node.name for node in neighbors}
    assert "src/app.py::build_app" in neighbor_names

    updated_repo = await store.get_repository_by_id(repository.id)
    assert updated_repo is not None
    assert updated_repo.relationships["graph_sync"]["payload_version"] == "2026-04-15"


@pytest.mark.asyncio
async def test_repository_graph_sync_returns_404_for_unknown_repo(
    admin_client: TestClient,
) -> None:
    response = admin_client.post(
        f"/v1/admin/repositories/{uuid.uuid4()}/graph-sync",
        json={"payload_version": "2026-04-15", "nodes": [], "edges": []},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_client_can_sync_repository_graph_with_client_key(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    graph_store: KnowledgeGraphStore,
    app: Any,
) -> None:
    auth = AuthService(store=store, config=config, cache=cache)
    admin, _ = await auth.register_user(
        email="client-sync-admin@example.com",
        username="client_sync_admin",
        display_name="Client Sync Admin",
        role=UserRole.ADMIN,
    )
    repository = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="client-sync-target",
        repo_url="https://example.com/client-sync-target",
        default_branch="main",
        state_path="/workspace/client-sync-target/.minder",
        context_snapshot={},
        relationships={},
    )
    _, client_api_key = await auth.register_client(
        name="Sync Client",
        slug="sync-client",
        created_by_user_id=admin.id,
        repo_scopes=["/workspace/client-sync-target"],
    )

    client = TestClient(app, raise_server_exceptions=True)
    response = client.post(
        f"/v1/client/repositories/{repository.id}/graph-sync",
        headers={"X-Minder-Client-Key": client_api_key},
        json={
            "payload_version": "2026-04-15",
            "repo_path": "/workspace/client-sync-target",
            "nodes": [
                {
                    "node_type": "controller",
                    "name": "src/api/controller.py::HealthController",
                    "metadata": {"language": "python"},
                },
                {
                    "node_type": "route",
                    "name": "GET /health",
                    "metadata": {"path": "/health", "method": "GET"},
                },
            ],
            "edges": [
                {
                    "source": {
                        "node_type": "controller",
                        "name": "src/api/controller.py::HealthController",
                    },
                    "target": {"node_type": "route", "name": "GET /health"},
                    "relation": "exposes_route",
                }
            ],
        },
    )

    assert response.status_code == 202
    route_node = await graph_store.get_node_by_name("route", "GET /health")
    assert route_node is not None


@pytest.mark.asyncio
async def test_client_graph_sync_rejects_repository_outside_scope(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    graph_store: KnowledgeGraphStore,
    app: Any,
) -> None:
    del graph_store
    auth = AuthService(store=store, config=config, cache=cache)
    admin, _ = await auth.register_user(
        email="scope-sync-admin@example.com",
        username="scope_sync_admin",
        display_name="Scope Sync Admin",
        role=UserRole.ADMIN,
    )
    repository = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="forbidden-sync-target",
        repo_url="https://example.com/forbidden-sync-target",
        default_branch="main",
        state_path="/workspace/forbidden-sync-target/.minder",
        context_snapshot={},
        relationships={},
    )
    _, client_api_key = await auth.register_client(
        name="Scoped Sync Client",
        slug="scoped-sync-client",
        created_by_user_id=admin.id,
        repo_scopes=["/workspace/other-repo"],
    )

    client = TestClient(app, raise_server_exceptions=True)
    response = client.post(
        f"/v1/client/repositories/{repository.id}/graph-sync",
        headers={"X-Minder-Client-Key": client_api_key},
        json={
            "payload_version": "2026-04-15",
            "repo_path": "/workspace/forbidden-sync-target",
            "nodes": [],
            "edges": [],
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_graph_sync_deletes_nodes_for_deleted_files(
    admin_client: TestClient,
    store: RelationalStore,
    graph_store: KnowledgeGraphStore,
) -> None:
    repository = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="delete-target",
        repo_url="https://example.com/delete-target",
        default_branch="main",
        state_path="/workspace/delete-target/.minder",
        context_snapshot={},
        relationships={},
    )

    initial_response = admin_client.post(
        f"/v1/admin/repositories/{repository.id}/graph-sync",
        json={
            "payload_version": "2026-04-15",
            "repo_path": "/workspace/delete-target",
            "branch": "main",
            "nodes": [
                {
                    "node_type": "file",
                    "name": "src/legacy.py",
                    "metadata": {"path": "src/legacy.py", "language": "python"},
                },
                {
                    "node_type": "function",
                    "name": "src/legacy.py::build_legacy",
                    "metadata": {"path": "src/legacy.py"},
                },
            ],
            "edges": [
                {
                    "source": {"node_type": "file", "name": "src/legacy.py"},
                    "target": {"node_type": "function", "name": "src/legacy.py::build_legacy"},
                    "relation": "contains",
                }
            ],
        },
    )

    assert initial_response.status_code == 202
    assert await graph_store.get_node_by_name("file", "src/legacy.py") is not None
    assert await graph_store.get_node_by_name("function", "src/legacy.py::build_legacy") is not None

    delete_response = admin_client.post(
        f"/v1/admin/repositories/{repository.id}/graph-sync",
        json={
            "payload_version": "2026-04-15",
            "repo_path": "/workspace/delete-target",
            "branch": "main",
            "deleted_files": ["src/legacy.py"],
            "nodes": [],
            "edges": [],
        },
    )

    assert delete_response.status_code == 202
    assert delete_response.json()["deleted_nodes"] == 2
    assert await graph_store.get_node_by_name("file", "src/legacy.py") is None
    assert await graph_store.get_node_by_name("function", "src/legacy.py::build_legacy") is None


@pytest.mark.asyncio
async def test_graph_sync_refresh_prunes_stale_nodes_for_changed_files(
    admin_client: TestClient,
    store: RelationalStore,
    graph_store: KnowledgeGraphStore,
) -> None:
    repository = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="refresh-target",
        repo_url="https://example.com/refresh-target",
        default_branch="main",
        state_path="/workspace/refresh-target/.minder",
        context_snapshot={},
        relationships={},
    )

    initial_response = admin_client.post(
        f"/v1/admin/repositories/{repository.id}/graph-sync",
        json={
            "payload_version": "2026-04-15",
            "repo_path": "/workspace/refresh-target",
            "branch": "main",
            "sync_metadata": {"changed_files": ["src/app.py"]},
            "nodes": [
                {
                    "node_type": "file",
                    "name": "src/app.py",
                    "metadata": {"path": "src/app.py", "language": "python"},
                },
                {
                    "node_type": "function",
                    "name": "src/app.py::old_handler",
                    "metadata": {"path": "src/app.py"},
                },
            ],
            "edges": [
                {
                    "source": {"node_type": "file", "name": "src/app.py"},
                    "target": {"node_type": "function", "name": "src/app.py::old_handler"},
                    "relation": "contains",
                }
            ],
        },
    )

    assert initial_response.status_code == 202
    assert await graph_store.get_node_by_name("function", "src/app.py::old_handler") is not None

    refresh_response = admin_client.post(
        f"/v1/admin/repositories/{repository.id}/graph-sync",
        json={
            "payload_version": "2026-04-15",
            "repo_path": "/workspace/refresh-target",
            "branch": "main",
            "sync_metadata": {"changed_files": ["src/app.py"]},
            "nodes": [
                {
                    "node_type": "file",
                    "name": "src/app.py",
                    "metadata": {"path": "src/app.py", "language": "python"},
                },
                {
                    "node_type": "function",
                    "name": "src/app.py::new_handler",
                    "metadata": {"path": "src/app.py"},
                },
            ],
            "edges": [
                {
                    "source": {"node_type": "file", "name": "src/app.py"},
                    "target": {"node_type": "function", "name": "src/app.py::new_handler"},
                    "relation": "contains",
                }
            ],
        },
    )

    assert refresh_response.status_code == 202
    assert refresh_response.json()["deleted_nodes"] == 2
    assert await graph_store.get_node_by_name("function", "src/app.py::old_handler") is None
    assert await graph_store.get_node_by_name("function", "src/app.py::new_handler") is not None
