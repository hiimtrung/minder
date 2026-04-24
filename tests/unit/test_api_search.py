from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.applications import Starlette
from starlette.testclient import TestClient

from minder.config import Settings
from minder.presentation.http.admin.context import AdminRouteContext
from minder.presentation.http.admin.search import build_search_routes
from minder.store.interfaces import IOperationalStore


def _skill_record(**overrides: object) -> SimpleNamespace:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "id": uuid.uuid4(),
        "title": "Testing skill",
        "content": "Reusable implementation pattern.",
        "language": "python",
        "tags": ["impl"],
        "embedding": [0.2, 0.1],
        "usage_count": 0,
        "quality_score": 0.5,
        "source_metadata": None,
        "excerpt_kind": "none",
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _build_client(store: AsyncMock) -> TestClient:
    context = AdminRouteContext.build(config=Settings(), store=store, cache=None)
    app = Starlette(routes=build_search_routes(context))
    app.state.config = Settings()
    return TestClient(app)


def test_skill_search_prefers_exact_language_and_tag_matches() -> None:
    store = AsyncMock(spec=IOperationalStore)
    client = _build_client(store)
    skills = [
        {
            "id": "rust-1",
            "title": "Rust Ownership",
            "content": "Borrow checker and ownership patterns.",
            "language": "rust",
            "tags": ["rust", "systems"],
            "workflow_step_tags": ["implementation"],
            "artifact_type_tags": [],
            "quality_score": 0.9,
        },
        {
            "id": "react-1",
            "title": "React Rendering",
            "content": "Component rendering and hydration.",
            "language": "typescript",
            "tags": ["react", "frontend"],
            "workflow_step_tags": ["implementation"],
            "artifact_type_tags": [],
            "quality_score": 0.9,
        },
    ]

    with patch.object(
        AdminRouteContext,
        "admin_user_from_request",
        new=AsyncMock(return_value=SimpleNamespace(id="admin")),
    ), patch(
        "minder.presentation.http.admin.search.SkillTools.minder_skill_list",
        new=AsyncMock(return_value=skills),
    ), patch(
        "minder.embedding.local.LocalEmbeddingProvider.embed",
        new=lambda self, value: [1.0 if "RUST" in value else 0.0, 0.0],
    ), patch(
        "minder.embedding.local.LocalEmbeddingProvider.embed_many",
        new=lambda self, values: [[1.0 if "rust" in v.lower() else 0.0, 0.0] for v in values],
    ):
        response = client.get("/v1/admin/search/skills?query=RUST")

        assert response.status_code == 200
        payload = response.json()
        assert payload["items"][0]["id"] == "rust-1"


def test_memories_search_includes_en_language_records() -> None:
    store = AsyncMock(spec=IOperationalStore)
    client = _build_client(store)
    store.list_skills.return_value = [
        _skill_record(title="English Memory", language="en", source_metadata=None),
        _skill_record(title="Python Skill", language="python", source_metadata=None),
    ]

    with patch.object(
        AdminRouteContext,
        "admin_user_from_request",
        new=AsyncMock(return_value=SimpleNamespace(id="admin")),
    ):
        response = client.get("/v1/admin/search/memories?query=&limit=20&offset=0")

    assert response.status_code == 200
    payload = response.json()
    titles = [item["title"] for item in payload["items"]]
    assert "English Memory" in titles
    assert "Python Skill" not in titles


def test_skills_search_excludes_en_memory_records() -> None:
    store = AsyncMock(spec=IOperationalStore)
    client = _build_client(store)
    store.list_skills.return_value = [
        _skill_record(title="English Memory", language="en", source_metadata=None),
        _skill_record(title="Python Skill", language="python", source_metadata=None),
    ]

    with patch.object(
        AdminRouteContext,
        "admin_user_from_request",
        new=AsyncMock(return_value=SimpleNamespace(id="admin")),
    ):
        response = client.get("/v1/admin/search/skills?query=&limit=20&offset=0")

    assert response.status_code == 200
    payload = response.json()
    titles = [item["title"] for item in payload["items"]]
    assert "English Memory" not in titles
    assert "Python Skill" in titles


def test_skill_search_falls_back_when_stored_embedding_dimensions_mismatch() -> None:
    store = AsyncMock(spec=IOperationalStore)
    client = _build_client(store)
    skills = [
        {
            "id": "go-1",
            "title": "Golang Concurrency",
            "content": "Use channels and contexts.",
            "language": "go",
            "tags": ["golang", "concurrency"],
            "workflow_step_tags": [],
            "artifact_type_tags": [],
            "quality_score": 0.8,
            "_embedding": [0.1, 0.2],  # stale/mismatched dimension
        }
    ]

    with patch.object(
        AdminRouteContext,
        "admin_user_from_request",
        new=AsyncMock(return_value=SimpleNamespace(id="admin")),
    ), patch(
        "minder.presentation.http.admin.search.SkillTools.minder_skill_list",
        new=AsyncMock(return_value=skills),
    ), patch(
        "minder.embedding.local.LocalEmbeddingProvider.embed",
        new=lambda self, value: [1.0, 0.0, 0.0],
    ), patch(
        "minder.embedding.local.LocalEmbeddingProvider.embed_many",
        new=lambda self, values: [
            [1.0, 0.0, 0.0] if "golang" in v.lower() else [0.0, 1.0, 0.0]
            for v in values
        ],
    ):
        response = client.get("/v1/admin/search/skills?query=golang")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["id"] == "go-1"
    assert payload["items"][0]["semantic_score"] > 0.0
