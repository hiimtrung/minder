from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from minder.config import MinderConfig
from minder.embedding.local import LocalEmbeddingProvider
from minder.graph.nodes.workflow_planner import WorkflowPlannerNode
from minder.graph.state import GraphState
from minder.prompts import PromptRegistry
from minder.resources import ResourceRegistry
from minder.retrieval.hybrid import HybridRetriever
from minder.retrieval.multi_hop import MultiHopRetriever
from minder.store.graph import KnowledgeGraphStore
from minder.store.relational import RelationalStore
from minder.store.vector import VectorStore
from minder.tools.ingest import IngestTools
from minder.tools.repo_scanner import RepoScanner

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


class MockFastMCPApp:
    def __init__(self) -> None:
        self._resources: dict[str, object] = {}
        self._prompts: dict[str, object] = {}

    def resource(self, uri: str, **kwargs: object):  # noqa: ANN003
        def decorator(fn: object) -> object:
            self._resources[uri] = fn
            return fn

        return decorator

    def prompt(self, name: str | None = None, **kwargs: object):  # noqa: ANN003
        def decorator(fn: object) -> object:
            key = name or getattr(fn, "__name__", "prompt")
            self._prompts[key] = fn
            return fn

        return decorator


def _reciprocal_rank(results: list[dict[str, Any]], relevant_suffixes: set[str]) -> float:
    for index, doc in enumerate(results, start=1):
        path = str(doc.get("path", ""))
        if any(path.endswith(suffix) for suffix in relevant_suffixes):
            return 1.0 / index
    return 0.0


def _make_repo_fixture(root: Path) -> tuple[Path, Path, Path]:
    orders = root / "orders"
    billing = root / "billing"
    orders.mkdir(parents=True)
    billing.mkdir(parents=True)

    (orders / "pyproject.toml").write_text(
        "[project]\nname = 'orders'\nversion = '0.1.0'\n",
        encoding="utf-8",
    )
    (billing / "pyproject.toml").write_text(
        "[project]\nname = 'billing'\nversion = '0.1.0'\n",
        encoding="utf-8",
    )
    (orders / "service.py").write_text(
        "from billing.client import charge_customer\n\n"
        "def checkout(order_id: str) -> str:\n"
        "    return charge_customer(order_id)\n",
        encoding="utf-8",
    )
    (billing / "client.py").write_text(
        '"""Billing client used by checkout flows."""\n\n'
        "def charge_customer(order_id: str) -> str:\n"
        "    return f'charged:{order_id}'\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Monorepo\n\n"
        "The orders service depends on the billing client.\n"
        "Checkout flows call charge_customer in billing/client.py.\n"
        "- [ ] review billing fallback\n",
        encoding="utf-8",
    )
    return root, orders, billing


def _init_local_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "phase3@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Phase 3 Gate"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest_asyncio.fixture
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
    settings = MinderConfig()
    settings.retrieval.top_k = 10
    settings.retrieval.similarity_threshold = 0.0
    settings.embedding.dimensions = 16
    return settings


async def _seed_phase3_context(store: RelationalStore, repo_path: Path) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    user = await store.create_user(
        id=uuid.uuid4(),
        email="phase3@example.com",
        username="phase3",
        display_name="Phase 3",
        api_key_hash="hash",
        role="member",
        is_active=True,
        settings={},
    )
    workflow = await store.create_workflow(
        id=uuid.uuid4(),
        name="tdd",
        version=1,
        steps=[
            {"name": "Test Writing"},
            {"name": "Implementation"},
            {"name": "Review"},
        ],
        policies={"block_step_skips": True},
        default_for_repo=True,
    )
    repo = await store.create_repository(
        id=uuid.uuid4(),
        repo_name=repo_path.name,
        repo_url="https://example.com/orders",
        default_branch="main",
        workflow_id=workflow.id,
        state_path=str(repo_path / ".minder"),
        context_snapshot={},
        relationships={},
    )
    session = await store.create_session(
        id=uuid.uuid4(),
        user_id=user.id,
        repo_id=repo.id,
        project_context={"repo_path": str(repo_path)},
        active_skills={},
        state={},
        ttl=3600,
    )
    await store.create_workflow_state(
        id=uuid.uuid4(),
        repo_id=repo.id,
        session_id=session.id,
        current_step="Test Writing",
        completed_steps=[],
        blocked_by=[],
        artifacts={"failing_tests": "orders/tests/test_checkout.py::test_charge_customer_retry"},
        next_step="Implementation",
    )
    return user.id, repo.id, session.id


@pytest.mark.asyncio
async def test_rag_pipeline_end_to_end(tmp_path: Path, store: RelationalStore, graph_store: KnowledgeGraphStore, config: MinderConfig) -> None:
    monorepo_root = tmp_path / "monorepo"
    repo_root, orders_dir, _billing_dir = _make_repo_fixture(monorepo_root)
    _init_local_git_repo(repo_root)

    _, repo_id, _session_id = await _seed_phase3_context(store, orders_dir)

    vector_store = VectorStore(store, store)
    embedder = LocalEmbeddingProvider(
        fastembed_model=config.embedding.fastembed_model,
        fastembed_cache_dir=config.embedding.fastembed_cache_dir,
        dimensions=16,
        runtime="mock",
    )
    ingest = IngestTools(store, embedder, vector_store=vector_store)

    # 1. Ingestion pipeline processes a real repository.
    git_result = await ingest.minder_ingest_git(str(repo_root))
    assert git_result["ingested_count"] >= 3
    assert any(path.endswith("README.md") for path in git_result["paths"])

    ingest_dir_result = await ingest.minder_ingest_directory(str(repo_root), project=repo_root.name)
    assert ingest_dir_result["ingested_count"] >= 3
    docs = await store.list_documents(project=repo_root.name)
    assert any(doc.source_path.endswith("README.md") for doc in docs)
    assert any(doc.source_path.endswith("client.py") for doc in docs)

    # 2. Multi-hop query across code + docs returns relevant cross-references.
    corpus = [
        {
            "path": doc.source_path,
            "title": doc.title,
            "content": doc.content,
            "score": float(doc.content.lower().count("billing") + doc.content.lower().count("charge_customer")),
            "doc_type": doc.doc_type,
        }
        for doc in docs
    ]

    async def lexical_retrieve(query: str, *, limit: int) -> list[dict[str, Any]]:
        query_terms = [term for term in query.lower().split() if len(term) > 2]
        ranked: list[dict[str, Any]] = []
        for doc in corpus:
            score = sum(doc["content"].lower().count(term) for term in query_terms)
            if score > 0:
                ranked.append({**doc, "score": float(score)})
        ranked.sort(key=lambda item: float(item["score"]), reverse=True)
        return ranked[:limit]

    multi_hop = MultiHopRetriever(lexical_retrieve, max_hops=2)
    cross_refs = await multi_hop.retrieve("checkout billing", limit=10)
    cross_ref_paths = {Path(str(doc["path"])).name for doc in cross_refs}
    assert "README.md" in cross_ref_paths
    assert "client.py" in cross_ref_paths

    # 3. Hybrid search improves MRR@10 over pure vector ranking.
    relevant_suffixes = {"README.md"}
    vector_only = [
        {"path": str(repo_root / "orders" / "service.py"), "content": "checkout entrypoint", "score": 0.95},
        {"path": str(repo_root / "billing" / "client.py"), "content": "charge_customer implementation", "score": 0.70},
        {
            "path": str(repo_root / "README.md"),
            "content": "orders service depends on billing client and documents charge_customer",
            "score": 0.15,
        },
    ]
    hybrid = HybridRetriever(alpha=0.2)
    hybrid_results = hybrid.merge(
        "orders billing charge_customer documentation",
        vector_only,
        vector_only,
        limit=10,
    )
    assert _reciprocal_rank(hybrid_results, relevant_suffixes) > _reciprocal_rank(vector_only, relevant_suffixes)

    # 4. Knowledge graph stores and queries repository relationships.
    scan_result = await RepoScanner(graph_store, str(repo_root), project=repo_root.name).scan()
    assert scan_result["files_scanned"] >= 2
    orders_node = await graph_store.get_node_by_name("service", "orders")
    billing_node = await graph_store.get_node_by_name("service", "billing")
    assert orders_node is not None
    assert billing_node is not None
    dependencies = await graph_store.get_neighbors(orders_node.id, direction="out", relation="depends_on")
    dependency_names = {node.name for node in dependencies}
    assert "billing" in dependency_names
    path = await graph_store.get_path(orders_node.id, billing_node.id)
    assert [node.name for node in path] == ["orders", "billing"]

    # 5. MCP resources and prompts are accessible.
    await store.create_skill(
        id=uuid.uuid4(),
        title="Billing Retry",
        content="Use charge_customer retry semantics for network failures.",
        language="markdown",
        tags=["billing", "retry"],
        embedding=[0.1] * 16,
        usage_count=0,
        quality_score=1.0,
    )
    await store.create_error(
        error_code="BILLING_TIMEOUT",
        error_message="billing dependency timed out",
        embedding=[0.2] * 16,
    )
    app = MockFastMCPApp()
    ResourceRegistry.register(app, store, graph_store=graph_store)  # type: ignore[arg-type]
    PromptRegistry.register(app)  # type: ignore[arg-type]

    skills_payload = json.loads(await app._resources["minder://skills"]())  # type: ignore[index,operator]
    repos_payload = json.loads(await app._resources["minder://repos"]())  # type: ignore[index,operator]
    stats_payload = json.loads(await app._resources["minder://stats"]())  # type: ignore[index,operator]
    structure_payload = json.loads(await app._resources["minder://repos/{repo_name}/structure"](repo_name=repo_root.name))  # type: ignore[index,operator]
    todos_payload = json.loads(await app._resources["minder://repos/{repo_name}/todos"](repo_name=repo_root.name))  # type: ignore[index,operator]
    tdd_prompt = await app._prompts["tdd_step"]("Test Writing")  # type: ignore[index,operator]

    assert any(item["title"] == "Billing Retry" for item in skills_payload)
    assert any(item["name"] == "orders" for item in repos_payload)
    assert stats_payload["skill_count"] >= 1
    assert stats_payload["repo_count"] >= 1
    assert structure_payload["counts"].get("service", 0) >= 2
    assert any(item["metadata"]["text"] == "review billing fallback" for item in todos_payload["items"])
    assert "Test Writing" in tdd_prompt[0]["content"]

    # 6. Workflow guidance includes dependency-aware context.
    planner = WorkflowPlannerNode(store, graph_store=graph_store)
    state = await planner.run(
        GraphState(
            query="fix checkout flow",
            repo_id=repo_id,
            repo_path=str(orders_dir),
            workflow_context={"workflow_name": "tdd"},
        )
    )
    guidance = state.workflow_context["guidance"]
    assert "Cross-service dependencies detected: billing" in guidance
    assert "Failing tests from last run:" in guidance
