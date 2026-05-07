from __future__ import annotations

import pytest

from minder.config import MinderConfig
from minder.graph.memory_graph import AgenticMemoryGraph
from minder.store.relational import RelationalStore
from minder.tools.memory import MemoryTools

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    settings = MinderConfig()
    settings.embedding.runtime = "mock"
    settings.memory.agentic_recall = True
    settings.memory.recall_min_score = 0.95
    settings.memory.recall_max_iterations = 3
    return settings


@pytest.mark.asyncio
async def test_agentic_memory_graph_loops_and_dedupes(
    store: RelationalStore,
    config: MinderConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = MemoryTools(store, config)
    await tools.minder_memory_store(
        title="JWT implementation note",
        content="Implement JWT refresh token rotation during the implementation step.",
        tags=["jwt", "implementation", "auth"],
        language="markdown",
    )
    graph = AgenticMemoryGraph(tools, config)
    monkeypatch.setattr(graph, "_judge_with_llm", lambda state, memories, fallback: None)

    result = await graph.run(
        {
            "original_query": "refresh token bug",
            "current_step": "Implementation",
            "artifact_type": None,
            "target_count": 1,
            "min_score": config.memory.recall_min_score,
            "all_memories": [],
            "search_queries": [],
            "current_query": "refresh token bug",
            "iteration": 0,
            "max_iterations": config.memory.recall_max_iterations,
            "latest_memories": [],
            "verdict": {},
            "final_memories": [],
            "recall_summary": "",
        }
    )

    assert len(result["search_queries"]) == config.memory.recall_max_iterations
    assert len(result["all_memories"]) > len(result["final_memories"])
    assert len(result["final_memories"]) == 1
    assert result["final_memories"][0]["title"] == "JWT implementation note"
    assert result["final_memories"][0]["recall_summary"].strip()


@pytest.mark.asyncio
async def test_agentic_memory_recall_preserves_best_ranked_memory(
    store: RelationalStore,
    config: MinderConfig,
) -> None:
    config.memory.recall_min_score = 0.4
    tools = MemoryTools(store, config)
    await tools.minder_memory_store(
        title="Test plan drafting",
        content="Write failing tests before implementation and capture the plan.",
        tags=["test", "test_plan"],
        language="markdown",
    )
    await tools.minder_memory_store(
        title="Release checklist",
        content="Prepare release notes and a rollback plan before deployment.",
        tags=["release"],
        language="markdown",
    )

    recalled = await tools.minder_memory_recall(
        "write tests before implementation",
        current_step="Test Writing",
        artifact_type="test_plan",
    )

    assert recalled[0]["title"] == "Test plan drafting"
    assert recalled[0]["score"] >= recalled[1]["score"]
    assert recalled[0]["step_compatibility"] > 0
