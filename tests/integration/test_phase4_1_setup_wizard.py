import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from pathlib import Path

from minder.config import MinderConfig
from minder.server import build_http_routes
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def test_store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


def _seed_dashboard_dist(dist: Path) -> None:
    (dist / "clients").mkdir(parents=True)
    (dist / "login").mkdir(parents=True)
    (dist / "setup").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>dashboard root</body></html>")
    (dist / "login" / "index.html").write_text("<html><body><h1>Admin Login</h1></body></html>")
    (dist / "setup" / "index.html").write_text("<html><body><h1>Create the first Minder admin</h1><form id='setup-form'></form></body></html>")

@pytest.mark.asyncio
async def test_setup_wizard_redirects_when_no_admin(test_store: RelationalStore, tmp_path: Path):
    config = MinderConfig()
    config.dashboard.legacy_compat_enabled = False
    dist = tmp_path / "dashboard-dist"
    _seed_dashboard_dist(dist)
    config.dashboard.static_dir = str(dist)
    routes = build_http_routes(config=config, store=test_store)
    app = Starlette(routes=routes)
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # Before setup, hitting dashboard should redirect to setup
        response = await client.get("/dashboard/login", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard/setup"

        response = await client.get("/setup")
        assert response.status_code == 308
        assert response.headers["location"] == "/dashboard/setup"

        # The setup page itself should load
        response = await client.get("/dashboard/setup")
        assert response.status_code == 200
        assert "Create the first Minder admin" in response.text
        
        response = await client.post("/v1/admin/setup", json={
            "username": "admin",
            "email": "test@minder.ai",
            "display_name": "Admin User",
        })
        assert response.status_code == 201
        assert response.json()["api_key"].startswith("mk_")
        
        response = await client.get("/dashboard/setup", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard/login"
        
        response = await client.get("/dashboard/login", follow_redirects=False)
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_setup_wizard_requires_only_api_key_model_fields(test_store: RelationalStore, tmp_path: Path):
    config = MinderConfig()
    config.dashboard.legacy_compat_enabled = False
    dist = tmp_path / "dashboard-dist"
    _seed_dashboard_dist(dist)
    config.dashboard.static_dir = str(dist)
    routes = build_http_routes(config=config, store=test_store)
    app = Starlette(routes=routes)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/dashboard/setup")

    assert response.status_code == 200
    assert "Create the first Minder admin" in response.text
    assert "setup-form" in response.text
    assert "password" not in response.text
