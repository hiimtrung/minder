from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.applications import Starlette
from starlette.testclient import TestClient

from minder.config import Settings
from minder.presentation.http.admin.context import AdminRouteContext
from minder.presentation.http.admin.search import build_search_routes
from minder.store.interfaces import IOperationalStore


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
