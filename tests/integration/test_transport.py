import pytest
import pytest_asyncio
from httpx import ASGITransport
from httpx import AsyncClient
from pathlib import Path
import subprocess
import uuid

from minder.bootstrap.transport import TOOL_DESCRIPTIONS, build_transport
from minder.auth.service import AuthService
from minder.auth.service import UserRole
from minder.config import MinderConfig
from minder.cache.providers import LRUCacheProvider
from minder.store.graph import KnowledgeGraphStore
from minder.store.relational import RelationalStore
from minder.transport import SSETransport, StdioTransport

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest_asyncio.fixture
async def graph_store() -> KnowledgeGraphStore:
    backend = KnowledgeGraphStore(IN_MEMORY_URL)
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
def auth(
    store: RelationalStore, config: MinderConfig, cache: LRUCacheProvider
) -> AuthService:
    return AuthService(store, config, cache=cache)


@pytest.mark.asyncio
async def test_sse_transport_rejects_missing_jwt_for_protected_tool(
    store: RelationalStore,
    config: MinderConfig,
    auth: AuthService,
    cache: LRUCacheProvider,
) -> None:
    transport = SSETransport(config=config, auth_service=auth, cache_provider=cache)

    async def whoami(*, user):  # noqa: ANN001, ANN202
        return {"user_id": str(user.id), "email": user.email}

    transport.register_tool("minder_auth_whoami", whoami, require_auth=True)

    with pytest.raises(Exception) as exc:
        await transport.call_tool("minder_auth_whoami")

    assert getattr(exc.value, "code", None) == "AUTH_MISSING_TOKEN"


@pytest.mark.asyncio
async def test_sse_transport_dispatches_tool_with_authenticated_user(
    store: RelationalStore,
    config: MinderConfig,
    auth: AuthService,
    cache: LRUCacheProvider,
) -> None:
    user, _ = await auth.register_user(
        email="transport@example.com",
        username="transport",
        display_name="Transport User",
    )
    token = auth.issue_jwt(user)
    transport = SSETransport(config=config, auth_service=auth, cache_provider=cache)

    async def whoami(*, user):  # noqa: ANN001, ANN202
        return {"user_id": str(user.id), "email": user.email, "role": user.role}

    transport.register_tool("minder_auth_whoami", whoami, require_auth=True)

    result = await transport.call_tool(
        "minder_auth_whoami",
        authorization=f"Bearer {token}",
    )

    assert result["email"] == "transport@example.com"
    assert result["role"] == "member"
    assert result["user_id"] == str(user.id)


@pytest.mark.asyncio
async def test_stdio_transport_uses_same_dispatch_contract(
    store: RelationalStore,
    config: MinderConfig,
    auth: AuthService,
    cache: LRUCacheProvider,
) -> None:
    user, _ = await auth.register_user(
        email="stdio@example.com",
        username="stdio",
        display_name="Stdio User",
    )
    token = auth.issue_jwt(user)
    transport = StdioTransport(config=config, auth_service=auth, cache_provider=cache)

    async def echo(*, message: str, user):  # noqa: ANN001, ANN202
        return {"message": message, "user_id": str(user.id)}

    transport.register_tool("echo", echo, require_auth=True)

    result = await transport.call_tool(
        "echo",
        arguments={"message": "hello"},
        authorization=f"Bearer {token}",
    )

    assert result == {"message": "hello", "user_id": str(user.id)}
    assert "echo" in transport.list_tools()


@pytest.mark.asyncio
async def test_stdio_transport_can_authenticate_client_principal_from_env(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = AuthService(store, config, cache=cache)
    admin, _ = await auth.register_user(
        email="stdio-client-admin@example.com",
        username="stdio_client_admin",
        display_name="Stdio Client Admin",
        role=UserRole.ADMIN,
    )
    _, client_api_key = await auth.register_client(
        name="Stdio Client",
        slug="stdio-client",
        created_by_user_id=admin.id,
        tool_scopes=["inspect_principal"],
    )
    monkeypatch.setenv("MINDER_CLIENT_API_KEY", client_api_key)
    transport = StdioTransport(config=config, auth_service=auth, cache_provider=cache)

    async def inspect_principal(*, principal):  # noqa: ANN001, ANN202
        return {
            "principal_type": principal.principal_type,
            "principal_id": str(principal.principal_id),
            "scopes": principal.scopes,
        }

    transport.register_tool("inspect_principal", inspect_principal, require_auth=True)

    result = await transport.call_tool("inspect_principal")

    assert result["principal_type"] == "client"
    assert result["scopes"] == ["inspect_principal"]


@pytest.mark.asyncio
async def test_stdio_transport_rejects_invalid_client_key_from_env(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = AuthService(store, config, cache=cache)
    monkeypatch.setenv("MINDER_CLIENT_API_KEY", "mkc_invalid_key")
    transport = StdioTransport(config=config, auth_service=auth, cache_provider=cache)

    async def inspect_principal(*, principal):  # noqa: ANN001, ANN202
        return {"principal_type": principal.principal_type}

    transport.register_tool("inspect_principal", inspect_principal, require_auth=True)

    with pytest.raises(Exception) as exc:
        await transport.call_tool("inspect_principal")

    assert getattr(exc.value, "code", None) == "AUTH_INVALID_CLIENT_KEY"


@pytest.mark.asyncio
async def test_sse_transport_dispatches_tool_with_authenticated_client_principal(
    store: RelationalStore, config: MinderConfig, cache: LRUCacheProvider
) -> None:
    auth = AuthService(store, config, cache=cache)
    admin, _ = await auth.register_user(
        email="principal-admin@example.com",
        username="principal_admin",
        display_name="Principal Admin",
        role=UserRole.ADMIN,
    )
    _, client_api_key = await auth.register_client(
        name="Codex Local",
        slug="codex-local",
        created_by_user_id=admin.id,
        tool_scopes=["inspect_principal"],
    )
    exchange = await auth.exchange_client_api_key(
        client_api_key,
        requested_scopes=["inspect_principal"],
    )
    transport = SSETransport(config=config, auth_service=auth, cache_provider=cache)

    async def inspect_principal(*, principal):  # noqa: ANN001, ANN202
        return {
            "principal_type": principal.principal_type,
            "principal_id": str(principal.principal_id),
            "scopes": principal.scopes,
        }

    transport.register_tool("inspect_principal", inspect_principal, require_auth=True)

    result = await transport.call_tool(
        "inspect_principal",
        authorization=f"Bearer {exchange['access_token']}",
    )

    assert result["principal_type"] == "client"
    assert result["scopes"] == ["inspect_principal"]


@pytest.mark.asyncio
async def test_build_transport_registers_descriptions_for_all_runtime_tools(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
) -> None:
    transport = build_transport(
        config=config, store=store, vector_store=store, cache=cache
    )

    assert set(transport.list_tools()) == set(TOOL_DESCRIPTIONS)
    assert all(transport._tools[name].description for name in transport.list_tools())


@pytest.mark.asyncio
async def test_build_transport_allows_client_memory_store_when_scoped(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
) -> None:
    auth = AuthService(store, config, cache=cache)
    admin, _ = await auth.register_user(
        email="memory-admin@example.com",
        username="memory_admin",
        display_name="Memory Admin",
        role=UserRole.ADMIN,
    )
    _, client_api_key = await auth.register_client(
        name="Memory Client",
        slug="memory-client",
        created_by_user_id=admin.id,
        tool_scopes=[
            "minder_memory_store",
            "minder_memory_list",
            "minder_memory_compact",
        ],
    )
    transport = build_transport(
        config=config, store=store, vector_store=store, cache=cache
    )

    stored = await transport.call_tool(
        "minder_memory_store",
        arguments={
            "title": "Transport memory",
            "content": "client principal can store memory",
            "tags": ["transport", "memory"],
            "language": "en",
        },
        client_key=client_api_key,
    )
    listed = await transport.call_tool(
        "minder_memory_list",
        client_key=client_api_key,
    )
    duplicate = await transport.call_tool(
        "minder_memory_store",
        arguments={
            "title": "Transport memory",
            "content": "client principal can store memory",
            "tags": ["transport", "memory", "duplicate"],
            "language": "en",
        },
        client_key=client_api_key,
    )
    compacted = await transport.call_tool(
        "minder_memory_compact",
        arguments={
            "memory_ids": [stored["id"], duplicate["id"]],
            "similarity_threshold": 0.8,
            "dry_run": True,
        },
        client_key=client_api_key,
    )

    assert stored["title"] == "Transport memory"
    assert any(entry["title"] == "Transport memory" for entry in listed)
    assert compacted["candidate_count"] == 2
    assert compacted["duplicate_group_count"] == 1


@pytest.mark.asyncio
async def test_build_transport_rejects_client_tool_outside_scope(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
) -> None:
    auth = AuthService(store, config, cache=cache)
    admin, _ = await auth.register_user(
        email="scope-admin@example.com",
        username="scope_admin",
        display_name="Scope Admin",
        role=UserRole.ADMIN,
    )
    _, client_api_key = await auth.register_client(
        name="Scoped Client",
        slug="scoped-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_memory_list"],
    )
    transport = build_transport(
        config=config, store=store, vector_store=store, cache=cache
    )

    with pytest.raises(Exception) as exc:
        await transport.call_tool(
            "minder_memory_store",
            arguments={
                "title": "Forbidden memory",
                "content": "should fail",
                "tags": ["transport"],
                "language": "en",
            },
            client_key=client_api_key,
        )

    assert getattr(exc.value, "code", None) == "AUTH_FORBIDDEN"


@pytest.mark.asyncio
async def test_build_transport_allows_client_skill_import_when_scoped(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "skill-transport-pack"
    repo_path.mkdir()
    skills_dir = repo_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "transport.md").write_text(
        "# Transport Imported Skill\n\nUse transport import coverage.",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Tests"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add transport skill pack"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    auth = AuthService(store, config, cache=cache)
    admin, _ = await auth.register_user(
        email="skill-import-admin@example.com",
        username="skill_import_admin",
        display_name="Skill Import Admin",
        role=UserRole.ADMIN,
    )
    _, client_api_key = await auth.register_client(
        name="Skill Import Client",
        slug="skill-import-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_skill_import_git", "minder_skill_list"],
    )
    transport = build_transport(
        config=config, store=store, vector_store=store, cache=cache
    )

    imported = await transport.call_tool(
        "minder_skill_import_git",
        arguments={
            "repo_url": str(repo_path),
            "source_path": "skills",
        },
        client_key=client_api_key,
    )
    listed = await transport.call_tool(
        "minder_skill_list",
        client_key=client_api_key,
    )

    assert imported["imported_count"] == 1
    assert any(item["title"] == "Transport Imported Skill" for item in listed)


@pytest.mark.asyncio
async def test_build_transport_allows_client_graph_impact_when_scoped(
    store: RelationalStore,
    graph_store: KnowledgeGraphStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    tmp_path,
) -> None:
    auth = AuthService(store, config, cache=cache)
    admin, _ = await auth.register_user(
        email="impact-admin@example.com",
        username="impact_admin",
        display_name="Impact Admin",
        role=UserRole.ADMIN,
    )
    repo_root = tmp_path / "impact-repo"
    repo_root.mkdir()

    source = await graph_store.upsert_node(
        node_type="file",
        name="app.py",
        metadata={"project": repo_root.name, "path": "app.py"},
    )
    function = await graph_store.upsert_node(
        node_type="function",
        name="app.py::checkout",
        metadata={"project": repo_root.name, "path": "app.py", "symbol": "checkout"},
    )
    route = await graph_store.upsert_node(
        node_type="route",
        name="POST /checkout",
        metadata={
            "project": repo_root.name,
            "path": "app.py",
            "route_path": "/checkout",
        },
    )
    await graph_store.upsert_edge(source.id, function.id, "contains")
    await graph_store.upsert_edge(function.id, route.id, "exposes_route")

    _, client_api_key = await auth.register_client(
        name="Impact Client",
        slug="impact-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_find_impact"],
        repo_scopes=[repo_root.name],
    )
    transport = build_transport(
        config=config,
        store=store,
        vector_store=store,
        graph_store=graph_store,
        cache=cache,
    )

    result = await transport.call_tool(
        "minder_find_impact",
        arguments={
            "target": "checkout",
            "repo_path": str(repo_root),
            "depth": 2,
            "limit": 10,
        },
        client_key=client_api_key,
    )

    assert result["matches"][0]["name"] == "app.py::checkout"
    assert any(item["name"] == "POST /checkout" for item in result["impacted"])


@pytest.mark.asyncio
async def test_build_transport_rejects_client_search_code_outside_repo_scope(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    tmp_path,
) -> None:
    auth = AuthService(store, config, cache=cache)
    admin, _ = await auth.register_user(
        email="search-admin@example.com",
        username="search_admin",
        display_name="Search Admin",
        role=UserRole.ADMIN,
    )
    allowed_repo = tmp_path / "allowed-repo"
    allowed_repo.mkdir()
    blocked_repo = tmp_path / "blocked-repo"
    blocked_repo.mkdir()

    _, client_api_key = await auth.register_client(
        name="Search Client",
        slug="search-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_search_code"],
        repo_scopes=[str(allowed_repo)],
    )
    transport = build_transport(
        config=config, store=store, vector_store=store, cache=cache
    )

    with pytest.raises(Exception) as exc:
        await transport.call_tool(
            "minder_search_code",
            arguments={"query": "checkout", "repo_path": str(blocked_repo), "limit": 5},
            client_key=client_api_key,
        )

    assert getattr(exc.value, "code", None) == "AUTH_FORBIDDEN"


@pytest.mark.asyncio
async def test_build_transport_rejects_client_query_outside_repo_scope(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    tmp_path,
) -> None:
    auth = AuthService(store, config, cache=cache)
    admin, _ = await auth.register_user(
        email="query-admin@example.com",
        username="query_admin",
        display_name="Query Admin",
        role=UserRole.ADMIN,
    )
    allowed_repo = tmp_path / "allowed-repo"
    allowed_repo.mkdir()
    blocked_repo = tmp_path / "blocked-repo"
    blocked_repo.mkdir()

    _, client_api_key = await auth.register_client(
        name="Query Client",
        slug="query-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_query"],
        repo_scopes=[str(allowed_repo)],
    )
    transport = build_transport(
        config=config, store=store, vector_store=store, cache=cache
    )

    with pytest.raises(Exception) as exc:
        await transport.call_tool(
            "minder_query",
            arguments={"query": "explain checkout", "repo_path": str(blocked_repo)},
            client_key=client_api_key,
        )

    assert getattr(exc.value, "code", None) == "AUTH_FORBIDDEN"


@pytest.mark.asyncio
async def test_build_transport_allows_client_graph_search_when_scoped(
    store: RelationalStore,
    graph_store: KnowledgeGraphStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    tmp_path,
) -> None:
    auth = AuthService(store, config, cache=cache)
    admin, _ = await auth.register_user(
        email="graph-search-admin@example.com",
        username="graph_search_admin",
        display_name="Graph Search Admin",
        role=UserRole.ADMIN,
    )
    repo_root = tmp_path / "graph-search-repo"
    repo_root.mkdir()

    await graph_store.upsert_node(
        node_type="function",
        name="service.py::checkout",
        metadata={
            "project": repo_root.name,
            "path": "service.py",
            "symbol": "checkout",
        },
    )
    await graph_store.upsert_node(
        node_type="route",
        name="POST /checkout",
        metadata={
            "project": repo_root.name,
            "path": "service.py",
            "route_path": "/checkout",
            "method": "POST",
        },
    )

    _, client_api_key = await auth.register_client(
        name="Graph Search Client",
        slug="graph-search-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_search_graph"],
        repo_scopes=[repo_root.name],
    )
    transport = build_transport(
        config=config,
        store=store,
        vector_store=store,
        graph_store=graph_store,
        cache=cache,
    )

    result = await transport.call_tool(
        "minder_search_graph",
        arguments={
            "query": "checkout",
            "repo_path": str(repo_root),
            "node_types": ["function", "route"],
            "limit": 10,
        },
        client_key=client_api_key,
    )

    assert result["count"] == 2
    assert [item["name"] for item in result["results"]] == [
        "service.py::checkout",
        "POST /checkout",
    ]


@pytest.mark.asyncio
async def test_build_transport_search_graph_follows_linked_repository_landscape(
    store: RelationalStore,
    graph_store: KnowledgeGraphStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    tmp_path,
) -> None:
    auth = AuthService(store, config, cache=cache)
    admin, _ = await auth.register_user(
        email="graph-landscape-admin@example.com",
        username="graph_landscape_admin",
        display_name="Graph Landscape Admin",
        role=UserRole.ADMIN,
    )
    repo_a_root = tmp_path / "repo-a"
    repo_a_root.mkdir()
    repo_b_root = tmp_path / "repo-b"
    repo_b_root.mkdir()

    repo_b = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="repo-b",
        repo_url="https://example.com/repo-b",
        default_branch="main",
        tracked_branches=["main"],
        state_path=str(repo_b_root / ".minder"),
        context_snapshot={},
        relationships={},
    )
    repo_a_id = uuid.uuid4()
    repo_a = await store.create_repository(
        id=repo_a_id,
        repo_name="repo-a",
        repo_url="https://example.com/repo-a",
        default_branch="main",
        tracked_branches=["main"],
        state_path=str(repo_a_root / ".minder"),
        context_snapshot={},
        relationships={
            "cross_repo_branches": [
                {
                    "id": "link-a-b-main",
                    "source_repo_id": str(repo_a_id),
                    "source_repo_name": "repo-a",
                    "source_branch": "main",
                    "target_repo_id": str(repo_b.id),
                    "target_repo_name": "repo-b",
                    "target_branch": "main",
                    "relation": "depends_on",
                    "direction": "outbound",
                    "confidence": 1.0,
                }
            ]
        },
    )

    await graph_store.upsert_node(
        node_type="function",
        name="orders.py::checkout",
        metadata={"project": "repo-a", "path": "orders.py", "symbol": "checkout"},
        repo_id=str(repo_a.id),
        branch="main",
    )
    await graph_store.upsert_node(
        node_type="function",
        name="payments.py::checkout_consumer",
        metadata={
            "project": "repo-b",
            "path": "payments.py",
            "symbol": "checkout_consumer",
        },
        repo_id=str(repo_b.id),
        branch="main",
    )

    _, client_api_key = await auth.register_client(
        name="Graph Landscape Client",
        slug="graph-landscape-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_search_graph"],
        repo_scopes=[repo_a_root.name, repo_b_root.name],
    )
    transport = build_transport(
        config=config,
        store=store,
        vector_store=store,
        graph_store=graph_store,
        cache=cache,
    )

    result = await transport.call_tool(
        "minder_search_graph",
        arguments={
            "query": "checkout",
            "repo_path": str(repo_a_root),
            "node_types": ["function"],
            "limit": 10,
        },
        client_key=client_api_key,
    )

    assert result["scope_count"] == 2
    assert {scope["repo_name"] for scope in result["searched_scopes"]} == {
        "repo-a",
        "repo-b",
    }
    assert {item["repo_name"] for item in result["results"]} == {"repo-a", "repo-b"}


@pytest.mark.asyncio
async def test_build_transport_find_impact_follows_linked_repository_landscape(
    store: RelationalStore,
    graph_store: KnowledgeGraphStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    tmp_path,
) -> None:
    auth = AuthService(store, config, cache=cache)
    admin, _ = await auth.register_user(
        email="impact-landscape-admin@example.com",
        username="impact_landscape_admin",
        display_name="Impact Landscape Admin",
        role=UserRole.ADMIN,
    )
    repo_a_root = tmp_path / "impact-a"
    repo_a_root.mkdir()
    repo_b_root = tmp_path / "impact-b"
    repo_b_root.mkdir()

    repo_b = await store.create_repository(
        id=uuid.uuid4(),
        repo_name="impact-b",
        repo_url="https://example.com/impact-b",
        default_branch="main",
        tracked_branches=["main"],
        state_path=str(repo_b_root / ".minder"),
        context_snapshot={},
        relationships={},
    )
    repo_a_id = uuid.uuid4()
    repo_a = await store.create_repository(
        id=repo_a_id,
        repo_name="impact-a",
        repo_url="https://example.com/impact-a",
        default_branch="main",
        tracked_branches=["main"],
        state_path=str(repo_a_root / ".minder"),
        context_snapshot={},
        relationships={
            "cross_repo_branches": [
                {
                    "id": "impact-link-a-b-main",
                    "source_repo_id": str(repo_a_id),
                    "source_repo_name": "impact-a",
                    "source_branch": "main",
                    "target_repo_id": str(repo_b.id),
                    "target_repo_name": "impact-b",
                    "target_branch": "main",
                    "relation": "depends_on",
                    "direction": "outbound",
                    "confidence": 1.0,
                }
            ]
        },
    )

    source = await graph_store.upsert_node(
        node_type="function",
        name="orders.py::checkout",
        metadata={"project": "impact-a", "path": "orders.py", "symbol": "checkout"},
        repo_id=str(repo_a.id),
        branch="main",
    )
    await graph_store.upsert_node(
        node_type="route",
        name="POST /checkout",
        metadata={
            "project": "impact-a",
            "path": "orders.py",
            "route_path": "/checkout",
        },
        repo_id=str(repo_a.id),
        branch="main",
    )
    linked_function = await graph_store.upsert_node(
        node_type="function",
        name="payments.py::checkout_consumer",
        metadata={
            "project": "impact-b",
            "path": "payments.py",
            "symbol": "checkout_consumer",
        },
        repo_id=str(repo_b.id),
        branch="main",
    )
    linked_route = await graph_store.upsert_node(
        node_type="route",
        name="POST /payments/checkout",
        metadata={
            "project": "impact-b",
            "path": "payments.py",
            "route_path": "/payments/checkout",
        },
        repo_id=str(repo_b.id),
        branch="main",
    )
    await graph_store.upsert_edge(linked_function.id, linked_route.id, "exposes_route")
    await graph_store.upsert_edge(source.id, linked_function.id, "cross_repo_calls")

    _, client_api_key = await auth.register_client(
        name="Impact Landscape Client",
        slug="impact-landscape-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_find_impact"],
        repo_scopes=[repo_a_root.name, repo_b_root.name],
    )
    transport = build_transport(
        config=config,
        store=store,
        vector_store=store,
        graph_store=graph_store,
        cache=cache,
    )

    result = await transport.call_tool(
        "minder_find_impact",
        arguments={
            "target": "checkout",
            "repo_path": str(repo_a_root),
            "depth": 2,
            "limit": 10,
        },
        client_key=client_api_key,
    )

    assert result["summary"]["scope_count"] == 2
    assert any(item["repo_name"] == "impact-b" for item in result["matches"])
    assert any(item["repo_name"] == "impact-b" for item in result["impacted"])
    linked_names = {item["name"] for item in result["matches"]} | {
        item["name"] for item in result["impacted"]
    }
    assert "POST /payments/checkout" in linked_names


@pytest.mark.asyncio
async def test_build_transport_rejects_client_graph_search_outside_repo_scope(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    tmp_path,
) -> None:
    auth = AuthService(store, config, cache=cache)
    admin, _ = await auth.register_user(
        email="graph-search-scope-admin@example.com",
        username="graph_search_scope_admin",
        display_name="Graph Search Scope Admin",
        role=UserRole.ADMIN,
    )
    allowed_repo = tmp_path / "allowed-graph-repo"
    allowed_repo.mkdir()
    blocked_repo = tmp_path / "blocked-graph-repo"
    blocked_repo.mkdir()

    _, client_api_key = await auth.register_client(
        name="Graph Search Scoped Client",
        slug="graph-search-scoped-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_search_graph"],
        repo_scopes=[str(allowed_repo)],
    )
    transport = build_transport(
        config=config, store=store, vector_store=store, cache=cache
    )

    with pytest.raises(Exception) as exc:
        await transport.call_tool(
            "minder_search_graph",
            arguments={"query": "checkout", "repo_path": str(blocked_repo), "limit": 5},
            client_key=client_api_key,
        )

    assert getattr(exc.value, "code", None) == "AUTH_FORBIDDEN"


@pytest.mark.asyncio
async def test_transport_enforces_rate_limit_for_member_user(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
) -> None:
    config.rate_limit.enabled = True
    config.rate_limit.member_limit = 1
    auth = AuthService(store, config, cache=cache)
    user, _ = await auth.register_user(
        email="rate-user@example.com",
        username="rate_user",
        display_name="Rate User",
    )
    token = auth.issue_jwt(user)
    transport = SSETransport(config=config, auth_service=auth, cache_provider=cache)

    async def echo(*, user, message: str):  # noqa: ANN001, ANN202
        return {"message": message, "user_id": str(user.id)}

    transport.register_tool("rate_echo", echo, require_auth=True)

    first = await transport.call_tool(
        "rate_echo",
        arguments={"message": "first"},
        authorization=f"Bearer {token}",
    )
    assert first["message"] == "first"

    with pytest.raises(Exception) as exc:
        await transport.call_tool(
            "rate_echo",
            arguments={"message": "second"},
            authorization=f"Bearer {token}",
        )

    assert getattr(exc.value, "code", None) == "AUTH_RATE_LIMITED"


@pytest.mark.asyncio
async def test_sse_transport_exposes_streamable_http_for_antigravity_compat(
    store: RelationalStore,
    config: MinderConfig,
    auth: AuthService,
    cache: LRUCacheProvider,
) -> None:
    transport = SSETransport(config=config, auth_service=auth, cache_provider=cache)
    app = transport.build_starlette_app()

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            streamable_headers = {"accept": "application/json, text/event-stream"}
            metadata = await client.get("/.well-known/oauth-protected-resource")
            mcp_initialize = await client.post(
                "/mcp",
                headers=streamable_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "antigravity", "version": "1.0.0"},
                    },
                },
            )
            sse_initialize = await client.post(
                "/sse",
                headers=streamable_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "antigravity", "version": "1.0.0"},
                    },
                },
            )

    assert metadata.status_code == 200
    assert metadata.json() == {
        "resource": "http://testserver/mcp",
        "authorization_servers": [],
    }
    assert mcp_initialize.status_code == 200
    assert sse_initialize.status_code == 200
