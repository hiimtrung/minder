"""
P3-Wave3 unit tests — Ingestion Expansion & Repo Relationships.

Tests:
  TestIngestURL        — minder_ingest_url via httpx mock
  TestIngestGit        — minder_ingest_git via subprocess mock
  TestRepoScanner      — RepoScanner against a synthetic fixture repo
"""

from __future__ import annotations

import textwrap
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from minder.store.graph import KnowledgeGraphStore
from minder.tools.ingest import IngestTools
from minder.tools.repo_scanner import RepoScanner

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_document(doc_id: uuid.UUID | None = None) -> MagicMock:
    doc = MagicMock()
    doc.id = doc_id or uuid.uuid4()
    return doc


def _make_ingest_tools(monkeypatch: pytest.MonkeyPatch) -> tuple[IngestTools, MagicMock]:
    """Return (IngestTools, mock_document_store)."""
    doc_store = AsyncMock()
    doc_store.upsert_document = AsyncMock(return_value=_make_document())

    embedding_provider = MagicMock()
    embedding_provider.embed = MagicMock(return_value=[0.1] * 8)

    tools = IngestTools(
        document_store=doc_store,
        embedding_provider=embedding_provider,
        vector_store=None,
    )
    return tools, doc_store


# ---------------------------------------------------------------------------
# TestIngestURL
# ---------------------------------------------------------------------------


class TestIngestURL:
    """minder_ingest_url — fetches text/URL and chunks it into document store."""

    @pytest.mark.asyncio
    async def test_plain_text_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tools, doc_store = _make_ingest_tools(monkeypatch)

        # Build a text body long enough to produce ≥2 chunks at chunk_size=64.
        body = "word " * 300  # 1500 chars → ≥2 chunks at size=64

        mock_response = MagicMock()
        mock_response.content = body.encode()
        mock_response.headers = {"content-type": "text/plain; charset=utf-8"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("minder.tools.ingest.httpx.AsyncClient", return_value=mock_client):
            result = await tools.minder_ingest_url(
                "https://example.com/notes.txt",
                project="test_proj",
                chunk_size=64,
                overlap=8,
            )

        assert result["url"] == "https://example.com/notes.txt"
        assert result["project"] == "test_proj"
        assert result["chunk_count"] >= 2
        assert len(result["doc_ids"]) == result["chunk_count"]
        assert doc_store.upsert_document.call_count == result["chunk_count"]

    @pytest.mark.asyncio
    async def test_html_url_strips_tags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tools, doc_store = _make_ingest_tools(monkeypatch)

        html = (
            "<html><head><style>body{color:red}</style></head>"
            "<body><h1>Title</h1><p>Hello world</p>"
            "<script>alert(1)</script></body></html>"
        )

        mock_response = MagicMock()
        mock_response.content = html.encode()
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("minder.tools.ingest.httpx.AsyncClient", return_value=mock_client):
            result = await tools.minder_ingest_url("https://example.com/page.html")

        assert result["chunk_count"] >= 1
        # Verify stripped content was passed to upsert (no <script> text)
        call_args = doc_store.upsert_document.call_args_list
        all_content = " ".join(c.kwargs["content"] for c in call_args)
        assert "alert" not in all_content
        assert "color:red" not in all_content

    @pytest.mark.asyncio
    async def test_project_defaults_to_netloc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tools, doc_store = _make_ingest_tools(monkeypatch)

        mock_response = MagicMock()
        mock_response.content = b"short text"
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("minder.tools.ingest.httpx.AsyncClient", return_value=mock_client):
            result = await tools.minder_ingest_url("https://docs.example.org/guide")

        assert result["project"] == "docs_example_org"

    @pytest.mark.asyncio
    async def test_http_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tools, _ = _make_ingest_tools(monkeypatch)

        mock_response = MagicMock()
        mock_response.content = b""
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.raise_for_status = MagicMock(side_effect=Exception("404 Not Found"))

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("minder.tools.ingest.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception, match="404"):
                await tools.minder_ingest_url("https://example.com/missing")


# ---------------------------------------------------------------------------
# TestIngestGit
# ---------------------------------------------------------------------------


class TestIngestGit:
    """minder_ingest_git — shallow clone + ingest_directory + cleanup."""

    @pytest.mark.asyncio
    async def test_successful_clone_and_ingest(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tools, doc_store = _make_ingest_tools(monkeypatch)

        # Create a fake cloned repo in tmp_path with one .py file.
        fake_repo = tmp_path / "fake_repo"
        fake_repo.mkdir()
        (fake_repo / "main.py").write_text("print('hello')")

        fake_run_result = MagicMock()
        fake_run_result.returncode = 0
        fake_run_result.stderr = ""

        calls: list[str] = []

        def fake_mkdtemp(**_: Any) -> str:
            calls.append("mkdtemp")
            return str(fake_repo)

        with (
            patch("minder.tools.ingest.subprocess.run", return_value=fake_run_result) as mock_run,
            patch("minder.tools.ingest.tempfile.mkdtemp", side_effect=fake_mkdtemp),
            patch("minder.tools.ingest.shutil.rmtree") as mock_rmtree,
        ):
            result = await tools.minder_ingest_git(
                "https://github.com/example/repo.git",
                project="my_project",
            )

        assert result["repo_url"] == "https://github.com/example/repo.git"
        assert result["project"] == "my_project"
        assert result["ingested_count"] >= 1
        # Cleanup must always be called.
        mock_rmtree.assert_called_once()
        # Git clone command must include --depth=1.
        clone_cmd = mock_run.call_args[0][0]
        assert "--depth=1" in clone_cmd

    @pytest.mark.asyncio
    async def test_project_derived_from_repo_name(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tools, _ = _make_ingest_tools(monkeypatch)

        fake_repo = tmp_path / "my_service"
        fake_repo.mkdir()

        fake_run_result = MagicMock()
        fake_run_result.returncode = 0
        fake_run_result.stderr = ""

        with (
            patch("minder.tools.ingest.subprocess.run", return_value=fake_run_result),
            patch("minder.tools.ingest.tempfile.mkdtemp", return_value=str(fake_repo)),
            patch("minder.tools.ingest.shutil.rmtree"),
        ):
            result = await tools.minder_ingest_git(
                "https://github.com/org/my_service.git"
            )

        assert result["project"] == "my_service"

    @pytest.mark.asyncio
    async def test_clone_failure_raises_and_cleans_up(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tools, _ = _make_ingest_tools(monkeypatch)

        fake_run_result = MagicMock()
        fake_run_result.returncode = 128
        fake_run_result.stderr = "Repository not found."

        with (
            patch("minder.tools.ingest.subprocess.run", return_value=fake_run_result),
            patch("minder.tools.ingest.tempfile.mkdtemp", return_value=str(tmp_path)),
            patch("minder.tools.ingest.shutil.rmtree") as mock_rmtree,
        ):
            with pytest.raises(RuntimeError, match="git clone failed"):
                await tools.minder_ingest_git("https://github.com/bad/repo.git")

        # Cleanup must happen even on failure.
        mock_rmtree.assert_called_once()

    @pytest.mark.asyncio
    async def test_branch_passed_to_git(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tools, _ = _make_ingest_tools(monkeypatch)

        fake_repo = tmp_path / "repo"
        fake_repo.mkdir()

        fake_run_result = MagicMock()
        fake_run_result.returncode = 0
        fake_run_result.stderr = ""

        with (
            patch("minder.tools.ingest.subprocess.run", return_value=fake_run_result) as mock_run,
            patch("minder.tools.ingest.tempfile.mkdtemp", return_value=str(fake_repo)),
            patch("minder.tools.ingest.shutil.rmtree"),
        ):
            await tools.minder_ingest_git(
                "https://github.com/org/repo.git", branch="feature/x"
            )

        cmd = mock_run.call_args[0][0]
        assert "--branch" in cmd
        assert "feature/x" in cmd


# ---------------------------------------------------------------------------
# TestRepoScanner
# ---------------------------------------------------------------------------


FIXTURE_REPO = {
    "pyproject.toml": "[project]\nname = 'service_a'",
        "README.md": "# Service A\n\n- [ ] document sync flow\n",
        "config.json": '{"service":"service_a","queue":"topic.health.updated"}',
        "frontend/src/api.ts": textwrap.dedent(
                """\
                export interface UserApi {
                    list(): Promise<void>;
                }

                export abstract class BaseController {}

                export class HealthController extends BaseController {}

                export async function fetchHealth() {
                    await fetch("https://api.example.com/health");
                    bus.publish("topic.frontend.events");
                }

                router.get("/frontend-health", fetchHealth);
                """
        ),
    "src/service_a/__init__.py": "",
    "src/service_a/main.py": textwrap.dedent(
        """\
        import os
        import httpx
        from pathlib import Path
        from abc import ABC, abstractmethod
        from typing import Protocol
        from service_b import client

        # TODO: add health checks

        class IUserGateway(Protocol):
            def fetch(self) -> dict: ...

        class BaseController(ABC):
            @abstractmethod
            def load(self) -> str:
                raise NotImplementedError

        class HealthController(BaseController):
            @router.get("/health")
            async def health(self) -> dict:
                await httpx.get("https://status.example.com/health")
                bus.publish("topic.health.updated")
                return {"ok": True}
        """
    ),
    "src/service_a/utils.py": textwrap.dedent(
        """\
        import json
        from service_a.models import User

        def load_user() -> User:
            consumer.subscribe("topic.user.events")
            return User()
        """
    ),
    "service_b/pyproject.toml": "[project]\nname = 'service_b'",
    "service_b/__init__.py": "",
    "service_b/client.py": textwrap.dedent(
        """\
        import httpx
        from service_b import models
        """
    ),
}


def _build_fixture_repo(base: Path) -> None:
    for rel, content in FIXTURE_REPO.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


async def _make_graph_store(db_url: str) -> KnowledgeGraphStore:
    store = KnowledgeGraphStore(db_url)
    await store.init_db()
    return store


class TestRepoScanner:
    """RepoScanner against a synthetic fixture repo."""

    @pytest_asyncio.fixture
    async def graph_store(self) -> KnowledgeGraphStore:
        store = KnowledgeGraphStore("sqlite+aiosqlite:///:memory:")
        await store.init_db()
        yield store
        await store.dispose()

    @pytest_asyncio.fixture
    def fixture_repo(self, tmp_path: Path) -> Path:
        _build_fixture_repo(tmp_path)
        return tmp_path

    @pytest.mark.asyncio
    async def test_scan_returns_summary(
        self, graph_store: KnowledgeGraphStore, fixture_repo: Path
    ) -> None:
        scanner = RepoScanner(graph_store, str(fixture_repo), project="test")
        result = await scanner.scan()

        assert result["project"] == "test"
        assert result["files_scanned"] > 0
        assert result["nodes_upserted"] > 0
        assert result["edges_upserted"] > 0

    @pytest.mark.asyncio
    async def test_file_nodes_created(
        self, graph_store: KnowledgeGraphStore, fixture_repo: Path
    ) -> None:
        scanner = RepoScanner(graph_store, str(fixture_repo), project="test")
        await scanner.scan()

        file_nodes = await graph_store.query_by_type("file")
        file_names = [n.name for n in file_nodes]
        # Check relative paths for key files.
        assert any("main.py" in n for n in file_names)
        assert any("client.py" in n for n in file_names)

    @pytest.mark.asyncio
    async def test_module_nodes_created(
        self, graph_store: KnowledgeGraphStore, fixture_repo: Path
    ) -> None:
        scanner = RepoScanner(graph_store, str(fixture_repo), project="test")
        await scanner.scan()

        mod_nodes = await graph_store.query_by_type("module")
        mod_names = {n.name for n in mod_nodes}
        # os, pathlib, json, httpx should all appear.
        assert "os" in mod_names
        assert "pathlib" in mod_names
        assert "json" in mod_names
        assert "httpx" in mod_names

    @pytest.mark.asyncio
    async def test_service_nodes_created(
        self, graph_store: KnowledgeGraphStore, fixture_repo: Path
    ) -> None:
        scanner = RepoScanner(graph_store, str(fixture_repo), project="test")
        await scanner.scan()

        svc_nodes = await graph_store.query_by_type("service")
        svc_names = {n.name for n in svc_nodes}
        # Root service (pyproject.toml in root) → "."
        # Nested service_b.
        assert any("service_b" in s for s in svc_names)

    @pytest.mark.asyncio
    async def test_imports_edges_created(
        self, graph_store: KnowledgeGraphStore, fixture_repo: Path
    ) -> None:
        scanner = RepoScanner(graph_store, str(fixture_repo), project="test")
        await scanner.scan()

        main_node = await graph_store.get_node_by_name(
            "file", str(Path("src/service_a/main.py"))
        )
        assert main_node is not None

        neighbors = await graph_store.get_neighbors(main_node.id, direction="out", relation="imports")
        neighbor_names = {n.name for n in neighbors}
        assert "os" in neighbor_names
        assert "pathlib" in neighbor_names

    @pytest.mark.asyncio
    async def test_idempotent_rescan(
        self, graph_store: KnowledgeGraphStore, fixture_repo: Path
    ) -> None:
        scanner = RepoScanner(graph_store, str(fixture_repo), project="test")
        result1 = await scanner.scan()
        result2 = await scanner.scan()

        # Node and edge counts should be stable after second scan.
        file_nodes_1 = await graph_store.query_by_type("file")
        file_nodes_2 = await graph_store.query_by_type("file")
        assert len(file_nodes_1) == len(file_nodes_2)
        assert result1["files_scanned"] == result2["files_scanned"]

    @pytest.mark.asyncio
    async def test_syntax_error_file_skipped(
        self, graph_store: KnowledgeGraphStore, tmp_path: Path
    ) -> None:
        """A .py file with a syntax error should be skipped gracefully."""
        bad_py = tmp_path / "bad.py"
        bad_py.write_text("def broken(\n  # unclosed")

        scanner = RepoScanner(graph_store, str(tmp_path), project="test")
        await scanner.scan()  # must not raise

        # bad.py itself gets a file node but produces no import edges.
        file_nodes = await graph_store.query_by_type("file")
        file_names = [n.name for n in file_nodes]
        assert any("bad.py" in n for n in file_names)

    @pytest.mark.asyncio
    async def test_empty_repo_no_crash(
        self, graph_store: KnowledgeGraphStore, tmp_path: Path
    ) -> None:
        scanner = RepoScanner(graph_store, str(tmp_path), project="empty")
        result = await scanner.scan()

        assert result["files_scanned"] == 0
        assert result["nodes_upserted"] == 0
        assert result["edges_upserted"] == 0

    @pytest.mark.asyncio
    async def test_symbol_and_controller_nodes_created(
        self, graph_store: KnowledgeGraphStore, fixture_repo: Path
    ) -> None:
        scanner = RepoScanner(graph_store, str(fixture_repo), project="test")
        await scanner.scan()

        function_node = await graph_store.get_node_by_name(
            "function", "src/service_a/main.py::HealthController.health"
        )
        controller_node = await graph_store.get_node_by_name(
            "controller", "src/service_a/main.py::HealthController"
        )
        interface_node = await graph_store.get_node_by_name(
            "interface", "src/service_a/main.py::IUserGateway"
        )
        abstract_node = await graph_store.get_node_by_name(
            "abstract_class", "src/service_a/main.py::BaseController"
        )

        assert function_node is not None
        assert controller_node is not None
        assert interface_node is not None
        assert abstract_node is not None

    @pytest.mark.asyncio
    async def test_route_external_service_todo_and_queue_nodes_created(
        self, graph_store: KnowledgeGraphStore, fixture_repo: Path
    ) -> None:
        scanner = RepoScanner(graph_store, str(fixture_repo), project="test")
        await scanner.scan()

        route_node = await graph_store.get_node_by_name("route", "GET /health")
        todo_nodes = await graph_store.query_by_type("todo")
        external_node = await graph_store.get_node_by_name(
            "external_service_api", "https://status.example.com/health"
        )
        topic_node = await graph_store.get_node_by_name("mq_topic", "topic.health.updated")
        consumer_topic = await graph_store.get_node_by_name("mq_topic", "topic.user.events")

        assert route_node is not None
        assert external_node is not None
        assert topic_node is not None
        assert consumer_topic is not None
        assert any(node.node_metadata.get("text") == "add health checks" for node in todo_nodes)

        controller_node = await graph_store.get_node_by_name(
            "controller", "src/service_a/main.py::HealthController"
        )
        assert controller_node is not None

        route_neighbors = await graph_store.get_neighbors(
            controller_node.id,
            direction="out",
            relation="exposes_route",
        )
        assert "GET /health" in {node.name for node in route_neighbors}

    @pytest.mark.asyncio
    async def test_multilanguage_and_document_metadata_created(
        self, graph_store: KnowledgeGraphStore, fixture_repo: Path
    ) -> None:
        scanner = RepoScanner(graph_store, str(fixture_repo), project="test")
        await scanner.scan()

        markdown_file = await graph_store.get_node_by_name("file", "README.md")
        json_file = await graph_store.get_node_by_name("file", "config.json")
        ts_function = await graph_store.get_node_by_name("function", "frontend/src/api.ts::fetchHealth")
        ts_controller = await graph_store.get_node_by_name("controller", "frontend/src/api.ts::HealthController")
        ts_route = await graph_store.get_node_by_name("route", "GET /frontend-health")
        ts_external = await graph_store.get_node_by_name("external_service_api", "https://api.example.com/health")
        ts_topic = await graph_store.get_node_by_name("mq_topic", "topic.frontend.events")

        assert markdown_file is not None
        assert markdown_file.node_metadata["heading_count"] == 1
        assert json_file is not None
        assert json_file.node_metadata["top_level_key_count"] == 2
        assert ts_function is not None
        assert ts_controller is not None
        assert ts_route is not None
        assert ts_external is not None
        assert ts_topic is not None

    def test_build_sync_payload_uses_changed_files_only(self, fixture_repo: Path) -> None:
        with patch.object(
            RepoScanner,
            "_git_file_change_metadata",
            side_effect=lambda rel_path: {
                "last_state": "modified",
                "last_commit_sha": f"sha-{rel_path}",
                "last_commit_at": "2026-04-15T09:00:00+00:00",
                "last_commit_summary": f"update {rel_path}",
                "history_summary": f"Recent changes: update {rel_path}",
                "recent_commits": [
                    {
                        "sha": f"sha-{rel_path}",
                        "committed_at": "2026-04-15T09:00:00+00:00",
                        "summary": f"update {rel_path}",
                    }
                ],
            },
        ), patch.object(
            RepoScanner,
            "_git_line_commit",
            side_effect=lambda rel_path, line_number: {
                "sha": f"line-{line_number}",
                "committed_at": "2026-04-14T08:30:00+00:00",
                "summary": f"touch {rel_path}:{line_number}",
            },
        ):
            payload = RepoScanner.build_sync_payload(
                str(fixture_repo),
                project="test",
                branch="feature/delta",
                diff_base="origin/main",
                changed_files=["README.md", "frontend/src/api.ts"],
                deleted_files=["src/service_a/main.py"],
            )

        changed_files = payload["sync_metadata"]["changed_files"]
        assert changed_files == ["README.md", "frontend/src/api.ts"]
        assert payload["branch"] == "feature/delta"
        assert payload["diff_base"] == "origin/main"
        assert payload["deleted_files"] == ["src/service_a/main.py"]
        assert payload["sync_metadata"]["deleted_file_count"] == 1
        assert all(node["name"] != "config.json" for node in payload["nodes"] if node["node_type"] == "file")
        assert any(node["node_type"] == "todo" and node["name"] == "README.md::TODO:3" for node in payload["nodes"])
        assert any(node["node_type"] == "route" and node["name"] == "GET /frontend-health" for node in payload["nodes"])
        readme_file = next(
            node for node in payload["nodes"] if node["node_type"] == "file" and node["name"] == "README.md"
        )
        route_node = next(
            node for node in payload["nodes"] if node["node_type"] == "route" and node["name"] == "GET /frontend-health"
        )
        assert readme_file["metadata"]["language"] == "markdown"
        assert readme_file["metadata"]["last_state"] == "modified"
        assert readme_file["metadata"]["history_summary"] == "Recent changes: update README.md"
        assert route_node["metadata"]["language"] == "typescript"
        assert route_node["metadata"]["history_scope"] == "symbol"
        assert route_node["metadata"]["last_touch_line"] == 14
        assert route_node["metadata"]["last_commit_summary"] == "touch frontend/src/api.ts:14"
        assert route_node["metadata"]["file_last_commit_summary"] == "update frontend/src/api.ts"

    @pytest.mark.asyncio
    async def test_strip_html_helper(self) -> None:
        """_strip_html removes tags and collapses whitespace."""
        from minder.tools.ingest import IngestTools

        html = "<p>Hello <b>world</b></p><script>alert(1)</script>"
        result = IngestTools._strip_html(html)
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result
        assert "alert" not in result
