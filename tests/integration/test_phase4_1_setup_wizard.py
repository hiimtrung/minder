import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from minder.config import MinderConfig
from minder.server import build_http_routes
from starlette.applications import Starlette
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def test_store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()

@pytest.mark.asyncio
async def test_setup_wizard_redirects_when_no_admin(test_store: RelationalStore):
    config = MinderConfig()
    routes = build_http_routes(config=config, store=test_store)
    app = Starlette(routes=routes)
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # Before setup, hitting dashboard should redirect to setup
        response = await client.get("/dashboard/login", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/setup"

        # The setup page itself should load
        response = await client.get("/setup")
        assert response.status_code == 200
        assert "Initial Admin Setup" in response.text
        
        # Post to setup
        response = await client.post("/setup", data={
            "username": "admin",
            "email": "test@minder.ai",
            "display_name": "Admin User",
        }, follow_redirects=False)
        
        if response.status_code == 400:
            print("400 Error Body:", response.text)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/dashboard-setup-complete?api_key=mk_")

        setup_complete_response = await client.get(response.headers["location"])
        assert setup_complete_response.status_code == 200
        assert "Copy this API key now" in setup_complete_response.text
        assert "mk_" in setup_complete_response.text
        
        # Now that an admin exists, setup should 403
        response = await client.get("/setup")
        assert response.status_code == 403
        
        # Dashboard login should no longer redirect
        response = await client.get("/dashboard/login", follow_redirects=False)
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_setup_wizard_requires_only_api_key_model_fields(test_store: RelationalStore):
    config = MinderConfig()
    routes = build_http_routes(config=config, store=test_store)
    app = Starlette(routes=routes)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/setup")

    assert response.status_code == 200
    assert "name=\"username\"" in response.text
    assert "name=\"email\"" in response.text
    assert "name=\"display_name\"" in response.text
    assert "name=\"password\"" not in response.text
