from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from minder.config import MinderConfig
from minder.server import build_http_app
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.mark.asyncio
async def test_phase4_3_console_gate_serves_static_dashboard_and_isolates_legacy_routes(
    store: RelationalStore,
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dashboard-dist"
    (dist / "clients").mkdir(parents=True)
    (dist / "login").mkdir(parents=True)
    (dist / "setup").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>console root</body></html>")
    (dist / "clients" / "index.html").write_text("<html><body>console clients</body></html>")
    (dist / "login" / "index.html").write_text("<html><body>console login</body></html>")
    (dist / "setup" / "index.html").write_text("<html><body>console setup</body></html>")

    config = MinderConfig(_env_file=None)
    config.dashboard.static_dir = str(dist)
    config.dashboard.legacy_compat_enabled = False
    config.dashboard.base_path = "/dashboard"

    app = build_http_app(config=config, store=store)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        dashboard_root = await client.get("/dashboard")
        dashboard_clients = await client.get("/dashboard/clients")
        dashboard_login = await client.get("/dashboard/login")
        legacy_console = await client.get("/console")
        legacy_console_clients = await client.get("/console/clients")
        legacy_setup = await client.get("/setup")
        client_detail = await client.get("/dashboard/clients/demo-client")

    assert dashboard_root.status_code == 303
    assert dashboard_root.headers["location"] == "/dashboard/setup"

    assert dashboard_clients.status_code == 303
    assert dashboard_clients.headers["location"] == "/dashboard/setup"

    assert dashboard_login.status_code == 303
    assert dashboard_login.headers["location"] == "/dashboard/setup"

    assert client_detail.status_code == 303
    assert client_detail.headers["location"] == "/dashboard/setup"

    assert legacy_console.status_code == 308
    assert legacy_console.headers["location"] == "/dashboard"

    assert legacy_console_clients.status_code == 308
    assert legacy_console_clients.headers["location"] == "/dashboard/clients"

    assert legacy_setup.status_code == 308
    assert legacy_setup.headers["location"] == "/dashboard/setup"


@pytest.mark.asyncio
async def test_phase4_3_console_gate_routes_dashboard_flow_by_setup_and_session_state(
    store: RelationalStore,
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dashboard-dist"
    (dist / "clients").mkdir(parents=True)
    (dist / "login").mkdir(parents=True)
    (dist / "setup").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>dashboard root</body></html>")
    (dist / "clients" / "index.html").write_text("<html><body>dashboard clients</body></html>")
    (dist / "login" / "index.html").write_text("<html><body>dashboard login</body></html>")
    (dist / "setup" / "index.html").write_text("<html><body>dashboard setup</body></html>")

    config = MinderConfig(_env_file=None)
    config.dashboard.static_dir = str(dist)
    config.dashboard.legacy_compat_enabled = False
    config.dashboard.base_path = "/dashboard"

    app = build_http_app(config=config, store=store)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        fresh_root = await client.get("/dashboard")
        fresh_setup = await client.get("/dashboard/setup")
        setup_response = await client.post(
            "/v1/admin/setup",
            json={
                "username": "admin",
                "email": "admin@example.com",
                "display_name": "Admin",
            },
        )
        api_key = setup_response.json()["api_key"]
        after_setup_root = await client.get("/dashboard")
        login_page = await client.get("/dashboard/login")
        login_response = await client.post("/v1/admin/login", json={"api_key": api_key})
        cookie_header = login_response.headers["set-cookie"]
        authed_root = await client.get("/dashboard", headers={"cookie": cookie_header})
        authed_clients = await client.get("/dashboard/clients", headers={"cookie": cookie_header})

    assert fresh_root.status_code == 303
    assert fresh_root.headers["location"] == "/dashboard/setup"
    assert fresh_setup.status_code == 200
    assert "dashboard setup" in fresh_setup.text

    assert after_setup_root.status_code == 303
    assert after_setup_root.headers["location"] == "/dashboard/login"
    assert login_page.status_code == 200
    assert "dashboard login" in login_page.text

    assert authed_root.status_code == 303
    assert authed_root.headers["location"] == "/dashboard/clients"
    assert authed_clients.status_code == 200
    assert "dashboard clients" in authed_clients.text


@pytest.mark.asyncio
async def test_phase4_3_console_gate_redirects_to_separate_dev_console_when_configured(
    store: RelationalStore,
) -> None:
    config = MinderConfig(_env_file=None)
    config.dashboard.base_path = "/dashboard"
    config.dashboard.dev_server_url = "http://localhost:8808/dashboard"
    app = build_http_app(config=config, store=store)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        dashboard_root = await client.get("/dashboard")
        dashboard_login = await client.get("/dashboard/login")
        setup_redirect = await client.get("/setup")

    assert dashboard_root.status_code == 307
    assert dashboard_root.headers["location"] == "http://localhost:8808/dashboard"
    assert dashboard_login.status_code == 307
    assert dashboard_login.headers["location"] == "http://localhost:8808/dashboard/login"
    assert setup_redirect.status_code == 308
    assert setup_redirect.headers["location"] == "http://localhost:8808/dashboard/setup"
