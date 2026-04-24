"""
Unit tests for Phase 3 Wave 4 — MCP Resources, Prompts & Workflow Intelligence.

Covers:
- ResourceRegistry.register() — skills, repos, stats resources
- PromptRegistry.register() — debug, review, explain, tdd_step prompts
- WorkflowPlannerNode with graph_store enrichment (P3-T12)
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from minder.graph.nodes.workflow_planner import WorkflowPlannerNode
from minder.graph.state import GraphState
from minder.prompts import PromptRegistry
from minder.resources import ResourceRegistry


# ---------------------------------------------------------------------------
# Helpers — mock FastMCP app that captures registrations
# ---------------------------------------------------------------------------


class MockFastMCPApp:
    """Minimal FastMCP stand-in that captures resource and prompt registrations."""

    def __init__(self) -> None:
        self._resources: dict[str, object] = {}  # uri → async handler
        self._prompts: dict[str, object] = {}    # name → handler

    def resource(self, uri: str, **kwargs: object):
        def decorator(fn: object) -> object:
            self._resources[uri] = fn
            return fn
        return decorator

    def prompt(self, name: str | None = None, **kwargs: object):
        def decorator(fn: object) -> object:
            key = name or fn.__name__  # type: ignore[union-attr]
            self._prompts[key] = fn
            return fn
        return decorator


# ---------------------------------------------------------------------------
# Helper — build a minimal mock store
# ---------------------------------------------------------------------------


def _make_skill(title: str, tags: list[str], language: str = "python") -> MagicMock:
    s = MagicMock()
    s.id = uuid.uuid4()
    s.title = title
    s.language = language
    s.tags = tags
    return s


def _make_repo(name: str, url: str = "https://example.com/repo") -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.repo_name = name
    r.repo_url = url
    return r


def _make_graph_node(
    node_type: str,
    name: str,
    *,
    project: str,
    metadata: dict[str, object] | None = None,
) -> MagicMock:
    node = MagicMock()
    node.id = uuid.uuid4()
    node.node_type = node_type
    node.name = name
    node.extra_metadata = {"project": project, **(metadata or {})}
    node.created_at = None
    return node


def _make_workflow_state(current_step: str = "Test Writing") -> MagicMock:
    ws = MagicMock()
    ws.current_step = current_step
    ws.completed_steps = []
    ws.blocked_by = []
    ws.artifacts = {}
    return ws


def _make_store(
    skills: list[MagicMock] | None = None,
    repos: list[MagicMock] | None = None,
    workflows: list[MagicMock] | None = None,
    errors: list[MagicMock] | None = None,
    workflow_states: dict[uuid.UUID, MagicMock] | None = None,
) -> MagicMock:
    store = MagicMock()
    store.list_skills = AsyncMock(return_value=skills or [])
    store.list_repositories = AsyncMock(return_value=repos or [])
    store.list_workflows = AsyncMock(return_value=workflows or [])
    store.list_errors = AsyncMock(return_value=errors or [])

    async def _get_wf_state(repo_id: uuid.UUID) -> MagicMock | None:
        return (workflow_states or {}).get(repo_id)

    store.get_workflow_state_by_repo = AsyncMock(side_effect=_get_wf_state)
    return store


# ===========================================================================
# ResourceRegistry tests
# ===========================================================================


class TestResourceRegistry:
    """Tests for ResourceRegistry.register()."""

    @pytest.fixture()
    def app(self) -> MockFastMCPApp:
        return MockFastMCPApp()

    # ------------------------------------------------------------------
    # minder://skills
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_skills_resource_returns_json_list(self, app: MockFastMCPApp) -> None:
        skills = [
            _make_skill("Clean Architecture", ["architecture", "design"]),
            _make_skill("NestJS Patterns", ["nestjs", "typescript"], language="typescript"),
        ]
        store = _make_store(skills=skills)
        ResourceRegistry.register(app, store)  # type: ignore[arg-type]

        handler = app._resources["minder://skills"]
        result = await handler()  # type: ignore[operator]

        data = json.loads(result)
        assert len(data) == 2
        titles = {item["title"] for item in data}
        assert titles == {"Clean Architecture", "NestJS Patterns"}
        assert data[0]["tags"] in (["architecture", "design"], ["nestjs", "typescript"])

    @pytest.mark.asyncio
    async def test_skills_resource_empty_store(self, app: MockFastMCPApp) -> None:
        store = _make_store(skills=[])
        ResourceRegistry.register(app, store)  # type: ignore[arg-type]

        handler = app._resources["minder://skills"]
        result = await handler()  # type: ignore[operator]
        assert json.loads(result) == []

    @pytest.mark.asyncio
    async def test_skills_resource_includes_language(self, app: MockFastMCPApp) -> None:
        skills = [_make_skill("Go Patterns", ["golang"], language="go")]
        store = _make_store(skills=skills)
        ResourceRegistry.register(app, store)  # type: ignore[arg-type]

        handler = app._resources["minder://skills"]
        result = await handler()  # type: ignore[operator]
        data = json.loads(result)
        assert data[0]["language"] == "go"

    # ------------------------------------------------------------------
    # minder://repos
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_repos_resource_with_workflow_state(self, app: MockFastMCPApp) -> None:
        repo = _make_repo("my-service")
        ws = _make_workflow_state("Implementation")
        store = _make_store(repos=[repo], workflow_states={repo.id: ws})
        ResourceRegistry.register(app, store)  # type: ignore[arg-type]

        handler = app._resources["minder://repos"]
        result = await handler()  # type: ignore[operator]
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["name"] == "my-service"
        assert data[0]["workflow_state"]["current_step"] == "Implementation"

    @pytest.mark.asyncio
    async def test_repos_resource_without_workflow_state(self, app: MockFastMCPApp) -> None:
        repo = _make_repo("orphan-repo")
        store = _make_store(repos=[repo], workflow_states={})
        ResourceRegistry.register(app, store)  # type: ignore[arg-type]

        handler = app._resources["minder://repos"]
        result = await handler()  # type: ignore[operator]
        data = json.loads(result)
        assert data[0]["workflow_state"] is None

    @pytest.mark.asyncio
    async def test_repos_resource_empty(self, app: MockFastMCPApp) -> None:
        store = _make_store(repos=[])
        ResourceRegistry.register(app, store)  # type: ignore[arg-type]

        handler = app._resources["minder://repos"]
        result = await handler()  # type: ignore[operator]
        assert json.loads(result) == []

    # ------------------------------------------------------------------
    # minder://stats
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_stats_resource_counts(self, app: MockFastMCPApp) -> None:
        store = _make_store(
            skills=[_make_skill("A", []), _make_skill("B", [])],
            repos=[_make_repo("r1"), _make_repo("r2"), _make_repo("r3")],
            workflows=[MagicMock()],
            errors=[MagicMock(), MagicMock()],
        )
        ResourceRegistry.register(app, store)  # type: ignore[arg-type]

        handler = app._resources["minder://stats"]
        result = await handler()  # type: ignore[operator]
        data = json.loads(result)
        assert data["skill_count"] == 2
        assert data["repo_count"] == 3
        assert data["workflow_count"] == 1
        assert data["error_count"] == 2

    @pytest.mark.asyncio
    async def test_stats_resource_all_zero(self, app: MockFastMCPApp) -> None:
        store = _make_store()
        ResourceRegistry.register(app, store)  # type: ignore[arg-type]

        handler = app._resources["minder://stats"]
        result = await handler()  # type: ignore[operator]
        data = json.loads(result)
        for val in data.values():
            assert val == 0

    # ------------------------------------------------------------------
    # Registration completeness
    # ------------------------------------------------------------------

    def test_all_three_resources_registered(self, app: MockFastMCPApp) -> None:
        store = _make_store()
        ResourceRegistry.register(app, store)  # type: ignore[arg-type]
        assert "minder://skills" in app._resources
        assert "minder://repos" in app._resources
        assert "minder://stats" in app._resources

    @pytest.mark.asyncio
    async def test_repo_structure_resource_groups_graph_nodes(self, app: MockFastMCPApp) -> None:
        store = _make_store()
        graph_store = MagicMock()
        graph_store.list_nodes = AsyncMock(
            return_value=[
                _make_graph_node("file", "app.py", project="orders", metadata={"path": "app.py"}),
                _make_graph_node("function", "app.py::checkout", project="orders", metadata={"path": "app.py", "symbol": "checkout"}),
                _make_graph_node("todo", "app.py::TODO:10", project="orders", metadata={"path": "app.py", "line": 10, "text": "wire retries"}),
                _make_graph_node("file", "other.py", project="billing", metadata={"path": "other.py"}),
            ]
        )
        ResourceRegistry.register(app, store, graph_store=graph_store)  # type: ignore[arg-type]

        handler = app._resources["minder://repos/{repo_name}/structure"]
        result = await handler(repo_name="orders")  # type: ignore[operator]
        data = json.loads(result)

        assert data["repo_name"] == "orders"
        assert data["counts"]["file"] == 1
        assert data["counts"]["function"] == 1
        assert data["counts"]["todo"] == 1

    @pytest.mark.asyncio
    async def test_repo_todos_resource_filters_to_repo(self, app: MockFastMCPApp) -> None:
        store = _make_store()
        graph_store = MagicMock()
        graph_store.list_nodes = AsyncMock(
            return_value=[
                _make_graph_node("todo", "orders/app.py::TODO:7", project="orders", metadata={"path": "orders/app.py", "line": 7, "text": "add metrics"}),
                _make_graph_node("todo", "billing/app.py::TODO:3", project="billing", metadata={"path": "billing/app.py", "line": 3, "text": "handle retries"}),
            ]
        )
        ResourceRegistry.register(app, store, graph_store=graph_store)  # type: ignore[arg-type]

        handler = app._resources["minder://repos/{repo_name}/todos"]
        result = await handler(repo_name="orders")  # type: ignore[operator]
        data = json.loads(result)

        assert data["count"] == 1
        assert data["items"][0]["metadata"]["text"] == "add metrics"

    @pytest.mark.asyncio
    async def test_repo_routes_resource_lists_graph_routes(self, app: MockFastMCPApp) -> None:
        store = _make_store()
        graph_store = MagicMock()
        graph_store.list_nodes = AsyncMock(
            return_value=[
                _make_graph_node("route", "GET /health", project="orders", metadata={"path": "api.py", "method": "GET", "route_path": "/health"}),
                _make_graph_node("route", "POST /checkout", project="orders", metadata={"path": "api.py", "method": "POST", "route_path": "/checkout"}),
                _make_graph_node("route", "GET /billing", project="billing", metadata={"path": "billing.py", "method": "GET", "route_path": "/billing"}),
            ]
        )
        ResourceRegistry.register(app, store, graph_store=graph_store)  # type: ignore[arg-type]

        handler = app._resources["minder://repos/{repo_name}/routes"]
        result = await handler(repo_name="orders")  # type: ignore[operator]
        data = json.loads(result)

        assert data["count"] == 2
        assert [item["name"] for item in data["items"]] == ["GET /health", "POST /checkout"]

    @pytest.mark.asyncio
    async def test_repo_symbols_resource_lists_symbol_nodes(self, app: MockFastMCPApp) -> None:
        store = _make_store()
        graph_store = MagicMock()
        graph_store.list_nodes = AsyncMock(
            return_value=[
                _make_graph_node("function", "api.py::checkout", project="orders", metadata={"path": "api.py", "symbol": "checkout"}),
                _make_graph_node("controller", "api.py::OrderController", project="orders", metadata={"path": "api.py", "symbol": "OrderController"}),
                _make_graph_node("route", "POST /checkout", project="orders", metadata={"path": "api.py", "route_path": "/checkout"}),
            ]
        )
        ResourceRegistry.register(app, store, graph_store=graph_store)  # type: ignore[arg-type]

        handler = app._resources["minder://repos/{repo_name}/symbols"]
        result = await handler(repo_name="orders")  # type: ignore[operator]
        data = json.loads(result)

        assert data["count"] == 2
        assert [item["node_type"] for item in data["items"]] == ["controller", "function"]


# ===========================================================================
# PromptRegistry tests
# ===========================================================================


class TestPromptRegistry:
    """Tests for PromptRegistry.register()."""

    @pytest.fixture()
    def app(self) -> MockFastMCPApp:
        a = MockFastMCPApp()
        PromptRegistry.register(a)  # type: ignore[arg-type]
        return a

    # ------------------------------------------------------------------
    # Registration completeness
    # ------------------------------------------------------------------

    def test_all_prompts_registered(self, app: MockFastMCPApp) -> None:
        assert "debug" in app._prompts
        assert "review" in app._prompts
        assert "explain" in app._prompts
        assert "tdd_step" in app._prompts

    # ------------------------------------------------------------------
    # debug prompt
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_debug_prompt_contains_error(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["debug"]
        messages = await fn(error="AttributeError: 'NoneType' has no attribute 'id'")  # type: ignore[operator]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "AttributeError" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_debug_prompt_includes_context_when_provided(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["debug"]
        messages = await fn(error="KeyError: 'foo'", context="Inside parse_config()")  # type: ignore[operator]
        content = messages[0]["content"]
        assert "parse_config" in content

    @pytest.mark.asyncio
    async def test_debug_prompt_no_context_by_default(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["debug"]
        messages = await fn(error="SomeError")  # type: ignore[operator]
        # Should not raise and should still include task
        assert "root cause" in messages[0]["content"].lower()

    # ------------------------------------------------------------------
    # review prompt
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_review_prompt_contains_diff(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["review"]
        messages = await fn(diff="+    x = 1")  # type: ignore[operator]
        assert "x = 1" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_review_prompt_includes_checklist_items(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["review"]
        messages = await fn(diff="-    pass")  # type: ignore[operator]
        content = messages[0]["content"]
        assert "Correctness" in content
        assert "Security" in content
        assert "BLOCKING" in content

    @pytest.mark.asyncio
    async def test_review_prompt_includes_context_when_provided(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["review"]
        messages = await fn(diff="+ foo()", context="Fixes issue #42")  # type: ignore[operator]
        assert "issue #42" in messages[0]["content"]

    # ------------------------------------------------------------------
    # explain prompt
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_explain_prompt_contains_code(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["explain"]
        messages = await fn(code="def add(a, b): return a + b")  # type: ignore[operator]
        assert "add(a, b)" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_explain_prompt_language_in_fence(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["explain"]
        messages = await fn(code="fn main() {}", language="rust")  # type: ignore[operator]
        assert "```rust" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_explain_prompt_default_language_python(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["explain"]
        messages = await fn(code="x = 1")  # type: ignore[operator]
        assert "```python" in messages[0]["content"]

    # ------------------------------------------------------------------
    # tdd_step prompt
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_tdd_step_test_writing_phase(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["tdd_step"]
        messages = await fn(current_step="Test Writing")  # type: ignore[operator]
        assert "Test Writing" in messages[0]["content"]
        assert "failing tests" in messages[0]["content"].lower()

    @pytest.mark.asyncio
    async def test_tdd_step_implementation_phase(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["tdd_step"]
        messages = await fn(current_step="Implementation")  # type: ignore[operator]
        assert "Implementation" in messages[0]["content"]
        assert "minimal code" in messages[0]["content"].lower()

    @pytest.mark.asyncio
    async def test_tdd_step_review_phase(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["tdd_step"]
        messages = await fn(current_step="Code Review")  # type: ignore[operator]
        assert "Review" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_tdd_step_unknown_step_generic_guidance(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["tdd_step"]
        messages = await fn(current_step="Deploy")  # type: ignore[operator]
        assert "Deploy" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_tdd_step_includes_failing_tests(self, app: MockFastMCPApp) -> None:
        fn = app._prompts["tdd_step"]
        messages = await fn(current_step="Test Writing", failing_tests="FAILED test_foo")  # type: ignore[operator]
        assert "FAILED test_foo" in messages[0]["content"]


# ===========================================================================
# WorkflowPlannerNode — graph-enriched guidance (P3-T12)
# ===========================================================================


class TestWorkflowPlannerNodeGraph:
    """Tests for the optional graph_store enrichment in WorkflowPlannerNode."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_base_store() -> MagicMock:
        store = MagicMock()
        store.get_workflow_by_name = AsyncMock(return_value=None)
        store.list_workflows = AsyncMock(return_value=[])
        store.get_workflow_state_by_repo = AsyncMock(return_value=None)
        return store

    @staticmethod
    def _make_graph_store(
        service_nodes: list[MagicMock] | None = None,
        dep_neighbors: list[MagicMock] | None = None,
    ) -> MagicMock:
        gs = MagicMock()
        gs.query_by_type = AsyncMock(return_value=service_nodes or [])
        gs.get_neighbors = AsyncMock(return_value=dep_neighbors or [])
        return gs

    @staticmethod
    def _make_service_node(name: str, path: str = "") -> MagicMock:
        n = MagicMock()
        n.id = uuid.uuid4()
        n.name = name
        n.extra_metadata = {"path": path}
        return n

    # ------------------------------------------------------------------
    # Backwards-compatibility: no graph_store
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_no_graph_store_uses_default_guidance(self) -> None:
        store = self._make_base_store()
        node = WorkflowPlannerNode(store)
        state = GraphState(query="q", repo_path="/repos/myapp")
        result = await node.run(state)
        guidance = result.workflow_context["guidance"]
        assert "Test Writing" in guidance
        # No cross-service line
        assert "Cross-service" not in guidance

    # ------------------------------------------------------------------
    # Graph store present, no matching service node
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_graph_store_no_matching_service_does_not_add_guidance(self) -> None:
        store = self._make_base_store()
        gs = self._make_graph_store(service_nodes=[])
        node = WorkflowPlannerNode(store, graph_store=gs)
        state = GraphState(query="q", repo_path="/repos/myapp")
        result = await node.run(state)
        guidance = result.workflow_context["guidance"]
        assert "Cross-service" not in guidance

    # ------------------------------------------------------------------
    # Graph store present, matching service node, with dependencies
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_graph_store_adds_dependency_guidance(self) -> None:
        store = self._make_base_store()
        svc = self._make_service_node("myapp", path="/repos/myapp")
        dep1 = MagicMock()
        dep1.name = "shared-lib"
        dep2 = MagicMock()
        dep2.name = "auth-service"
        gs = self._make_graph_store(service_nodes=[svc], dep_neighbors=[dep1, dep2])
        node = WorkflowPlannerNode(store, graph_store=gs)
        state = GraphState(query="q", repo_path="/repos/myapp")
        result = await node.run(state)
        guidance = result.workflow_context["guidance"]
        assert "Cross-service dependencies detected" in guidance
        assert "auth-service" in guidance
        assert "shared-lib" in guidance

    # ------------------------------------------------------------------
    # Graph store present, no cross-service deps
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_graph_store_no_deps_no_extra_guidance(self) -> None:
        store = self._make_base_store()
        svc = self._make_service_node("myapp")
        gs = self._make_graph_store(service_nodes=[svc], dep_neighbors=[])
        node = WorkflowPlannerNode(store, graph_store=gs)
        state = GraphState(query="q", repo_path="/repos/myapp")
        result = await node.run(state)
        guidance = result.workflow_context["guidance"]
        assert "Cross-service" not in guidance

    # ------------------------------------------------------------------
    # Failing tests in workflow artifacts are appended
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_graph_store_appends_failing_tests_from_artifacts(self) -> None:
        store = self._make_base_store()
        ws = _make_workflow_state("Implementation")
        ws.artifacts = {"failing_tests": "test_foo FAILED"}
        store.get_workflow_state_by_repo = AsyncMock(return_value=ws)

        svc = self._make_service_node("myapp", path="/repos/myapp")
        gs = self._make_graph_store(service_nodes=[svc], dep_neighbors=[])
        node = WorkflowPlannerNode(store, graph_store=gs)
        repo_id = uuid.uuid4()
        state = GraphState(query="q", repo_path="/repos/myapp", repo_id=repo_id)
        result = await node.run(state)
        guidance = result.workflow_context["guidance"]
        assert "test_foo FAILED" in guidance

    # ------------------------------------------------------------------
    # No repo_path → graph store not consulted
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_graph_store_skipped_when_no_repo_path(self) -> None:
        store = self._make_base_store()
        gs = self._make_graph_store()
        node = WorkflowPlannerNode(store, graph_store=gs)
        state = GraphState(query="q")  # no repo_path
        await node.run(state)
        gs.query_by_type.assert_not_called()

    # ------------------------------------------------------------------
    # Graph store exception is swallowed gracefully
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_graph_store_exception_does_not_break_pipeline(self) -> None:
        store = self._make_base_store()
        gs = MagicMock()
        gs.query_by_type = AsyncMock(side_effect=RuntimeError("db exploded"))
        node = WorkflowPlannerNode(store, graph_store=gs)
        state = GraphState(query="q", repo_path="/repos/myapp")
        # Should complete without raising
        result = await node.run(state)
        assert "guidance" in result.workflow_context
