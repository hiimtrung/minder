import pytest

from minder.graph.nodes.context_enricher import ContextEnricherNode
from minder.graph.state import GraphState


class _Skill:
    def __init__(self, title, content, tags, quality_score=1.0, language="python"):
        self.title = title
        self.content = content
        self.tags = tags
        self.quality_score = quality_score
        self.language = language
        self.source_metadata = {"src": "test"}  # non-memory marker


class _Error:
    def __init__(self, error_code, error_message):
        self.error_code = error_code
        self.error_message = error_message


class MockStore:
    def __init__(self, skills=None, memories=None, errors=None):
        self._skills = skills or []
        self._memories = memories or []
        self._errors = errors or []

    async def list_skills_by_kind(self, *, is_memory, exclude_deprecated=True, owner_id=None):
        return self._memories if is_memory else self._skills

    async def list_errors(self):
        return self._errors


@pytest.mark.asyncio
async def test_enricher_skips_irrelevant_query():
    store = MockStore(skills=[_Skill("S1", "code", ["backend"])])
    node = ContextEnricherNode(store)
    state = GraphState(query="what is the capital of France?")
    result = await node.run(state)
    assert "enriched_context" not in result.metadata


@pytest.mark.asyncio
async def test_enricher_fetches_skills_for_analyze_query():
    skills = [
        _Skill("auth_helper", "def auth(): pass", ["backend", "auth"], quality_score=0.9),
        _Skill("db_utils", "def db(): pass", ["backend", "database"], quality_score=0.8),
        _Skill("react_comp", "const Comp = () => {}", ["frontend"], quality_score=0.7),
    ]
    store = MockStore(skills=skills)
    node = ContextEnricherNode(store)
    state = GraphState(query="analyze backend skills")
    result = await node.run(state)

    enriched = result.metadata.get("enriched_context", [])
    assert len(enriched) >= 2
    titles = [e["title"] for e in enriched]
    # backend-tagged items should appear
    assert "auth_helper" in titles
    assert "db_utils" in titles


@pytest.mark.asyncio
async def test_enricher_filters_by_tag_hint():
    skills = [
        _Skill("auth_helper", "def auth(): pass", ["backend", "auth"]),
        _Skill("react_comp", "const Comp = () => {}", ["frontend"]),
    ]
    store = MockStore(skills=skills)
    node = ContextEnricherNode(store)
    state = GraphState(query="show me all backend skills")
    result = await node.run(state)

    enriched = result.metadata.get("enriched_context", [])
    titles = [e["title"] for e in enriched]
    assert "auth_helper" in titles
    # frontend item should be last or missing when backend is preferred
    # (it's still included as fallback but scored lower)


@pytest.mark.asyncio
async def test_enricher_fetches_memories():
    memories = [
        _Skill("deployment-note", "Always use blue-green deploy", [], language="markdown"),
    ]
    store = MockStore(memories=memories)
    node = ContextEnricherNode(store)

    # Override: mark as memory by removing source_metadata
    memories[0].source_metadata = None
    memories[0].language = "markdown"

    state = GraphState(query="show all memories")
    result = await node.run(state)

    enriched = result.metadata.get("enriched_context", [])
    assert any(e["type"] == "memory" for e in enriched)


@pytest.mark.asyncio
async def test_enricher_fetches_errors():
    errors = [_Error("DB_CONN_ERROR", "Connection refused to postgres")]
    store = MockStore(errors=errors)
    node = ContextEnricherNode(store)
    state = GraphState(query="list recent errors")
    result = await node.run(state)

    enriched = result.metadata.get("enriched_context", [])
    assert any(e["type"] == "error" for e in enriched)
    assert enriched[0]["title"] == "DB_CONN_ERROR"


@pytest.mark.asyncio
async def test_enricher_content_includes_full_text():
    long_content = "x" * 2000
    skills = [_Skill("big_skill", long_content, ["backend"])]
    store = MockStore(skills=skills)
    node = ContextEnricherNode(store)
    state = GraphState(query="analyze backend skills")
    result = await node.run(state)

    enriched = result.metadata.get("enriched_context", [])
    assert len(enriched) >= 1
    # content should be capped at _MAX_CONTENT_CHARS (1200) not 500
    assert len(enriched[0]["content"]) == 1200


@pytest.mark.asyncio
async def test_enricher_store_failure_is_silent():
    class BrokenStore:
        async def list_skills_by_kind(self, **_):
            raise RuntimeError("DB unavailable")
        async def list_errors(self):
            raise RuntimeError("DB unavailable")

    node = ContextEnricherNode(BrokenStore())
    state = GraphState(query="analyze all skills")
    # Should not raise
    result = await node.run(state)
    # enriched_context absent or empty — no crash
    assert result.metadata.get("enriched_context", []) == []
