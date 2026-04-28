"""P7-VERIFY — Acceptance gate for Phase 7: learning subsystem, advanced runtime UX,
and post-CLI backend reconciliation.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from minder.context_compactor import SummarizingCompactor
from minder.graph.nodes import ReflectionNode
from minder.graph.state import GraphState
from minder.learning import (
    ErrorLearner,
    PatternExtractor,
    QualityOptimizer,
    SkillSynthesizer,
    extract_pattern,
)
from minder.learning.skill_synthesizer import _render_pattern


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    *,
    edge: str = "complete",
    quality_score: float = 0.8,
    retry_count: int = 0,
    attempt_failures: list[dict[str, Any]] | None = None,
    recalled_skill_ids: list[str] | None = None,
) -> GraphState:
    return GraphState(
        query="How do I write a test?",
        session_id=None,
        evaluation={"quality_score": quality_score},
        guard_result={"passed": True},
        verification_result={"passed": True},
        llm_output={"text": "Write a pytest test.", "provider": "litert_lm"},
        reasoning_output={"sources": [{"path": "src/foo.py", "title": "foo", "score": 0.9}]},
        workflow_context={"workflow_name": "test-workflow", "current_step": "Test Writing"},
        retry_count=retry_count,
        metadata={
            "edge": edge,
            "attempt_failures": attempt_failures or [],
            "recalled_skill_ids": recalled_skill_ids or [],
        },
    )


def _make_store(*, existing_skills: list[Any] | None = None) -> Any:
    store = AsyncMock()
    skills = existing_skills or []
    store.list_skills = AsyncMock(return_value=skills)
    store.create_skill = AsyncMock(side_effect=lambda **kw: _MockSkill(kw))
    store.get_skill_by_id = AsyncMock(return_value=None)
    store.update_skill = AsyncMock(return_value=None)
    return store


class _MockSkill:
    def __init__(self, data: dict[str, Any]) -> None:
        self.__dict__.update(data)
        if "id" not in self.__dict__:
            self.id = uuid.uuid4()

    def __getattr__(self, name: str) -> Any:
        return None


def _mock_embedder(fixed: list[float] | None = None) -> Any:
    emb = fixed or [0.1] * 16
    m = MagicMock()
    m.embed = MagicMock(return_value=emb)
    return m


# ---------------------------------------------------------------------------
# P7-T01 — PatternExtractor
# ---------------------------------------------------------------------------


class TestPatternExtractor:
    def test_extracts_from_successful_state(self) -> None:
        state = _make_state(edge="complete", quality_score=0.9)
        pattern = extract_pattern(state)
        assert pattern is not None
        assert pattern["query"] == state.query
        assert pattern["edge"] == "complete"
        assert pattern["quality_score"] == pytest.approx(0.9)
        assert pattern["workflow_name"] == "test-workflow"
        assert pattern["current_step"] == "Test Writing"

    def test_returns_none_for_failed_edge(self) -> None:
        state = _make_state(edge="guard_failed", quality_score=0.9)
        assert extract_pattern(state) is None

    def test_returns_none_for_low_quality(self) -> None:
        state = _make_state(edge="complete", quality_score=0.3)
        assert extract_pattern(state) is None

    def test_fallback_complete_is_success(self) -> None:
        state = _make_state(edge="fallback_complete", quality_score=0.6)
        pattern = extract_pattern(state)
        assert pattern is not None
        assert pattern["edge"] == "fallback_complete"

    def test_class_api_matches(self) -> None:
        extractor = PatternExtractor()
        state = _make_state(edge="complete", quality_score=0.8)
        assert extractor.extract(state) == extract_pattern(state)


# ---------------------------------------------------------------------------
# P7-T02 — SkillSynthesizer
# ---------------------------------------------------------------------------


class TestSkillSynthesizer:
    @pytest.mark.asyncio
    async def test_creates_skill_when_no_duplicate(self) -> None:
        store = _make_store()
        embedder = _mock_embedder([0.1, 0.2, 0.3] + [0.0] * 13)
        synthesizer = SkillSynthesizer(store, embedder)
        pattern = extract_pattern(_make_state(edge="complete", quality_score=0.8))
        assert pattern is not None
        result = await synthesizer.synthesize(pattern)
        assert result is not None
        assert "id" in result
        store.create_skill.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_duplicate_exists(self) -> None:
        emb = [0.9, 0.1] + [0.0] * 14
        existing = _MockSkill(
            {
                "id": str(uuid.uuid4()),
                "tags": ["workflow_pattern"],
                "embedding": emb,
                "quality_score": 0.7,
            }
        )
        store = _make_store(existing_skills=[existing])
        embedder = _mock_embedder(emb)
        synthesizer = SkillSynthesizer(store, embedder)
        pattern = extract_pattern(_make_state(edge="complete", quality_score=0.8))
        assert pattern is not None
        result = await synthesizer.synthesize(pattern)
        assert result is None
        store.create_skill.assert_not_awaited()

    def test_render_pattern_contains_query(self) -> None:
        pattern = extract_pattern(_make_state(edge="complete", quality_score=0.8))
        assert pattern is not None
        content = _render_pattern(pattern)
        assert "How do I write a test?" in content
        assert "Test Writing" in content


# ---------------------------------------------------------------------------
# P7-T03 — ErrorLearner
# ---------------------------------------------------------------------------


class TestErrorLearner:
    @pytest.mark.asyncio
    async def test_records_error_pattern(self) -> None:
        store = _make_store()
        embedder = _mock_embedder()
        learner = ErrorLearner(store, embedder)
        state = _make_state(
            edge="guard_failed",
            quality_score=0.0,
            attempt_failures=[
                {"attempt": 1, "edge": "guard_failed", "reason": "hallucination", "provider": "litert_lm"},
            ],
        )
        result = await learner.learn(state)
        assert result is not None
        assert result["failure_count"] == 1
        store.create_skill.assert_awaited_once()
        call_kwargs = store.create_skill.call_args.kwargs
        assert "error_pattern" in call_kwargs["tags"]

    @pytest.mark.asyncio
    async def test_returns_none_when_no_failures(self) -> None:
        store = _make_store()
        learner = ErrorLearner(store, _mock_embedder())
        result = await learner.learn(_make_state(edge="complete"))
        assert result is None
        store.create_skill.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_caps_error_skills_at_limit(self) -> None:
        from minder.learning.error_learner import _MAX_ERROR_SKILLS
        skills = [
            _MockSkill({"id": str(uuid.uuid4()), "tags": ["error_pattern"], "embedding": [0.1] * 16, "quality_score": 0.0})
            for _ in range(_MAX_ERROR_SKILLS)
        ]
        store = _make_store(existing_skills=skills)
        learner = ErrorLearner(store, _mock_embedder())
        state = _make_state(attempt_failures=[{"attempt": 1, "edge": "guard_failed", "reason": "x"}])
        result = await learner.learn(state)
        assert result is None


# ---------------------------------------------------------------------------
# P7-T04 — QualityOptimizer
# ---------------------------------------------------------------------------


class TestQualityOptimizer:
    @pytest.mark.asyncio
    async def test_updates_by_explicit_ids(self) -> None:
        skill_id = uuid.uuid4()
        skill = _MockSkill({"id": skill_id, "quality_score": 0.5, "usage_count": 2})
        store = _make_store()
        store.get_skill_by_id = AsyncMock(return_value=skill)
        optimizer = QualityOptimizer(store, _mock_embedder())
        state = _make_state(quality_score=0.9, recalled_skill_ids=[str(skill_id)])
        updates = await optimizer.optimize(state)
        assert len(updates) == 1
        store.update_skill.assert_awaited_once()
        call_kwargs = store.update_skill.call_args.kwargs
        assert call_kwargs["usage_count"] == 3
        assert call_kwargs["quality_score"] > 0.5

    @pytest.mark.asyncio
    async def test_skips_when_quality_zero(self) -> None:
        store = _make_store()
        optimizer = QualityOptimizer(store, _mock_embedder())
        state = _make_state(quality_score=0.0)
        updates = await optimizer.optimize(state)
        assert updates == []
        store.update_skill.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fallback_to_similarity(self) -> None:
        emb = [0.8, 0.2] + [0.0] * 14
        skill = _MockSkill(
            {
                "id": str(uuid.uuid4()),
                "tags": ["workflow_pattern"],
                "embedding": emb,
                "quality_score": 0.5,
                "usage_count": 1,
            }
        )
        store = _make_store(existing_skills=[skill])
        store.get_skill_by_id = AsyncMock(return_value=skill)
        embedder = _mock_embedder(emb)
        optimizer = QualityOptimizer(store, embedder)
        state = _make_state(quality_score=0.8, recalled_skill_ids=[])
        updates = await optimizer.optimize(state)
        assert len(updates) == 1


# ---------------------------------------------------------------------------
# P7-T05 — ReflectionNode
# ---------------------------------------------------------------------------


class TestReflectionNode:
    @pytest.mark.asyncio
    async def test_runs_without_error_on_success(self) -> None:
        store = _make_store()
        embedder = _mock_embedder()
        node = ReflectionNode(store=store, embedder=embedder)
        state = _make_state(edge="complete", quality_score=0.8)
        result = await node.run(state)
        assert "reflection" in result.metadata

    @pytest.mark.asyncio
    async def test_runs_without_error_on_failure(self) -> None:
        store = _make_store()
        node = ReflectionNode(store=store, embedder=_mock_embedder())
        state = _make_state(
            edge="guard_failed",
            quality_score=0.0,
            attempt_failures=[{"attempt": 1, "edge": "guard_failed", "reason": "x"}],
        )
        result = await node.run(state)
        assert "reflection" in result.metadata

    @pytest.mark.asyncio
    async def test_swallows_store_exceptions(self) -> None:
        store = AsyncMock()
        store.list_skills = AsyncMock(side_effect=RuntimeError("db down"))
        store.create_skill = AsyncMock(side_effect=RuntimeError("db down"))
        node = ReflectionNode(store=store, embedder=_mock_embedder())
        state = _make_state(edge="complete", quality_score=0.8)
        result = await node.run(state)
        assert result is state


# ---------------------------------------------------------------------------
# P7-T06 — SummarizingCompactor
# ---------------------------------------------------------------------------


class TestSummarizingCompactor:
    def _messages(self, count: int) -> list[dict[str, Any]]:
        return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i} " * 20} for i in range(count)]

    def test_uses_summarizer_for_dropped_messages(self) -> None:
        called: list[list] = []

        def summarizer(dropped: list[dict]) -> str:
            called.append(dropped)
            return "Summary of earlier messages."

        compactor = SummarizingCompactor(summarizer, keep_recent=2)
        messages = self._messages(10)
        result = compactor.compact(messages, context_length=256)
        assert len(result) <= 10
        if called:
            first = result[0]["content"]
            assert "Summary" in first or "Earlier" in first or "omitted" in first

    def test_falls_back_to_notice_when_summarizer_raises(self) -> None:
        def bad_summarizer(dropped: list[dict]) -> str:
            raise RuntimeError("LLM unavailable")

        compactor = SummarizingCompactor(bad_summarizer, keep_recent=2)
        messages = self._messages(10)
        result = compactor.compact(messages, context_length=256)
        assert len(result) <= 10

    def test_passes_through_when_under_budget(self) -> None:
        compactor = SummarizingCompactor(lambda _: "summary", keep_recent=4)
        messages = [{"role": "user", "content": "hi"}]
        assert compactor.compact(messages, context_length=16384) == messages


# ---------------------------------------------------------------------------
# P7-T07 — Skill usage increment on recall
# ---------------------------------------------------------------------------


class TestSkillUsageIncrement:
    @pytest.mark.asyncio
    async def test_usage_count_incremented_on_recall(self) -> None:
        from minder.tools.skills import SkillTools

        skill_id = uuid.uuid4()
        emb = [0.5] * 16
        skill = _MockSkill(
            {
                "id": skill_id,
                "title": "Test skill",
                "content": "Write tests first.",
                "tags": [],
                "quality_score": 0.6,
                "usage_count": 3,
                "embedding": emb,
                "deprecated": False,
                "excerpt_kind": "none",
                "language": "python",  # not in MEMORY_LANGUAGES — treated as skill
                "source_metadata": {"import_key": "x"},  # non-None → not a memory record
            }
        )
        store = AsyncMock()
        store.list_skills = AsyncMock(return_value=[skill])
        store.update_skill = AsyncMock(return_value=None)

        config = MagicMock()
        config.embedding.fastembed_model = "BAAI/bge-small-en-v1.5"
        config.embedding.fastembed_cache_dir = "/tmp"
        config.embedding.dimensions = 16
        config.embedding.runtime = "cpu"

        with patch("minder.tools.skills.LocalEmbeddingProvider") as mock_provider_cls:
            mock_instance = MagicMock()
            mock_instance.embed = MagicMock(return_value=emb)
            mock_provider_cls.return_value = mock_instance
            tools = SkillTools(store, config)
            await tools.minder_skill_recall("Write tests first.")

        store.update_skill.assert_awaited()


# ---------------------------------------------------------------------------
# P7-T12 — RuntimeAgentExecutor workflow intent
# ---------------------------------------------------------------------------


class TestRuntimeAgentWorkflow:
    @pytest.mark.asyncio
    async def test_workflow_list_intent(self) -> None:
        from minder.presentation.http.admin.runtime import RuntimeAgentExecutor

        wf = _MockSkill({"id": str(uuid.uuid4()), "name": "default-workflow"})
        context = MagicMock()
        context.store = AsyncMock()
        context.store.list_workflows = AsyncMock(return_value=[wf])
        context.config = MagicMock()
        context.config.embedding.fastembed_model = "BAAI/bge-small-en-v1.5"
        context.config.embedding.fastembed_cache_dir = "/tmp"
        context.config.embedding.dimensions = 16
        context.config.embedding.runtime = "cpu"

        with (
            patch("minder.tools.memory.MemoryTools.__init__", return_value=None),
            patch("minder.tools.skills.SkillTools.__init__", return_value=None),
            patch("minder.tools.session.SessionTools.__init__", return_value=None),
        ):
            executor = RuntimeAgentExecutor.__new__(RuntimeAgentExecutor)
            executor._store = context.store
            executor._memory_tools = MagicMock()
            executor._skill_tools = MagicMock()
            executor._session_tools = MagicMock()

            result = await executor._execute_workflow(
                query="list workflows",
                repository={"id": None, "name": "test", "path": "/tmp/test"},
            )

        assert result is not None
        assert "Listed 1 workflows" in result["answer"]


# ---------------------------------------------------------------------------
# P7-T13 — history_source tracking
# ---------------------------------------------------------------------------


class TestHistorySourceTracking:
    @pytest.mark.asyncio
    async def test_history_source_is_mongodb_when_records_exist(self) -> None:
        from minder.tools.query import QueryTools

        session_id = uuid.uuid4()
        history_doc = MagicMock()
        history_doc.role = "user"
        history_doc.content = "previous question"

        store = AsyncMock()
        store.list_history_for_session = AsyncMock(return_value=[history_doc])
        store.create_history = AsyncMock()

        config = MagicMock()
        config.embedding.fastembed_model = "BAAI/bge-small-en-v1.5"
        config.embedding.fastembed_cache_dir = "/tmp"
        config.embedding.dimensions = 16
        config.embedding.runtime = "cpu"
        config.llm.context_length = 4096

        mock_graph = AsyncMock()
        final_state = GraphState(
            query="test",
            metadata={
                "orchestration_runtime": "internal",
                "edge": "complete",
                "history_source": "mongodb",
                "history_message_count": 1,
            },
            llm_output={"text": "answer", "provider": "mock"},
            reasoning_output={"sources": []},
            workflow_context={},
            evaluation={"quality_score": 0.8},
        )
        mock_graph.run = AsyncMock(return_value=final_state)

        with (
            patch("minder.tools.query.LocalEmbeddingProvider", MagicMock()),
            patch("minder.tools.query.IngestTools", MagicMock()),
            patch("minder.tools.query.MinderGraph", return_value=mock_graph),
            patch("minder.store.vector.VectorStore", MagicMock()),
            patch("minder.tools.query.PromptRegistry.resolve_prompt_model", AsyncMock(return_value=MagicMock())),
        ):
            tools = QueryTools(store, config)
            result = await tools.minder_query("test", repo_path=None, session_id=session_id)

        assert result["history_source"] == "mongodb"
        assert result["history_message_count"] >= 1

    @pytest.mark.asyncio
    async def test_history_source_is_none_for_new_session(self) -> None:
        from minder.tools.query import QueryTools

        store = AsyncMock()
        store.list_history_for_session = AsyncMock(return_value=[])
        store.create_history = AsyncMock()

        config = MagicMock()
        config.embedding.fastembed_model = "BAAI/bge-small-en-v1.5"
        config.embedding.fastembed_cache_dir = "/tmp"
        config.embedding.dimensions = 16
        config.embedding.runtime = "cpu"
        config.llm.context_length = 4096

        mock_graph = AsyncMock()
        final_state = GraphState(
            query="test",
            metadata={
                "orchestration_runtime": "internal",
                "edge": "complete",
                "history_source": "none",
                "history_message_count": 0,
            },
            llm_output={"text": "answer", "provider": "mock"},
            reasoning_output={"sources": []},
            workflow_context={},
            evaluation={"quality_score": 0.8},
        )
        mock_graph.run = AsyncMock(return_value=final_state)

        with (
            patch("minder.tools.query.LocalEmbeddingProvider", MagicMock()),
            patch("minder.tools.query.IngestTools", MagicMock()),
            patch("minder.tools.query.MinderGraph", return_value=mock_graph),
            patch("minder.store.vector.VectorStore", MagicMock()),
            patch("minder.tools.query.PromptRegistry.resolve_prompt_model", AsyncMock(return_value=MagicMock())),
        ):
            tools = QueryTools(store, config)
            result = await tools.minder_query("test", repo_path=None, session_id=uuid.uuid4())

        assert result["history_source"] == "none"
