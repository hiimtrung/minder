from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from starlette.applications import Starlette
from starlette.testclient import TestClient

from minder.config import Settings
from minder.presentation.http.admin.context import AdminRouteContext
from minder.presentation.http.admin.memories import build_memories_routes
from minder.store.interfaces import IOperationalStore


def _memory(**overrides: object) -> SimpleNamespace:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "id": uuid.uuid4(),
        "title": "Testing memory",
        "content": "Some persistent knowledge.",
        "language": "markdown",
        "tags": ["test"],
        "source_metadata": None,
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _build_client(store: AsyncMock) -> TestClient:
    context = AdminRouteContext.build(config=Settings(), store=store, cache=None)
    app = Starlette(routes=build_memories_routes(context))
    app.state.config = Settings()
    return TestClient(app)


def test_list_memories_includes_human_languages() -> None:
    store = AsyncMock(spec=IOperationalStore)
    # Mocking different languages
    memories = [
        _memory(title="Markdown Memory", language="markdown"),
        _memory(title="English Memory", language="en"),
        _memory(title="Vietnamese Memory", language="vi"),
        _memory(title="Python Skill", language="python"), # Should be filtered out
    ]
    store.list_skills.return_value = memories
    client = _build_client(store)

    response = client.get("/api/v1/memories")

    assert response.status_code == 200
    payload = response.json()
    
    # Check that human languages are included
    titles = [item["title"] for item in payload]
    assert "Markdown Memory" in titles
    assert "English Memory" in titles
    assert "Vietnamese Memory" in titles
    
    # Check that programming languages are excluded
    assert "Python Skill" not in titles
    
    # Total should be 3
    assert len(payload) == 3

def test_list_memories_excludes_imported_skills() -> None:
    store = AsyncMock(spec=IOperationalStore)
    memories = [
        _memory(title="Local Memory", source_metadata=None),
        _memory(title="Imported Skill", source_metadata={"repo": "git"}), # Should be filtered out
    ]
    store.list_skills.return_value = memories
    client = _build_client(store)

    response = client.get("/api/v1/memories")

    assert response.status_code == 200
    payload = response.json()
    
    titles = [item["title"] for item in payload]
    assert "Local Memory" in titles
    assert "Imported Skill" not in titles
    assert len(payload) == 1
