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
def app(store: RelationalStore, config: MinderConfig, cache: LRUCacheProvider) -> Any:
    return build_http_app(config=config, store=store, cache=cache)


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
