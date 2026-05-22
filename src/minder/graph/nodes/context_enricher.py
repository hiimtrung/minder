from __future__ import annotations

import logging
from typing import Any

from minder.graph.state import GraphState
from minder.store.interfaces import IOperationalStore

logger = logging.getLogger(__name__)

# Nouns that identify a data type the user is asking about
_SKILL_NOUNS = frozenset({
    "skill", "skills", "kỹ năng", "snippet", "snippets", "function",
    "method", "pattern", "utility", "helper", "code pattern",
})
_MEMORY_NOUNS = frozenset({
    "memory", "memories", "note", "notes", "tài liệu", "kiến thức",
    "ghi chú", "lưu ý", "reminder", "fact", "facts",
})
_ERROR_NOUNS = frozenset({
    "error", "errors", "bug", "bugs", "exception", "lỗi", "issue",
    "issues", "problem", "problems", "crash",
})

# Verbs / phrases that signal the user wants analysis / enumeration
_ANALYSIS_VERBS = frozenset({
    "analyze", "analysis", "phân tích", "tóm tắt", "summarize", "summary",
    "list", "liệt kê", "show", "give me", "tôi có", "what", "how many",
    "xem", "tất cả", "all", "overview", "review", "explain",
    "mô tả", "kể", "nêu", "describe", "tell me", "breakdown",
})

# Tech tags that can appear as query words
_KNOWN_TAGS = [
    "backend", "frontend", "api", "database", "auth", "authentication",
    "authorization", "testing", "deployment", "ci", "cd", "docker",
    "kubernetes", "k8s", "python", "javascript", "typescript", "react",
    "fastapi", "django", "flask", "sqlalchemy", "redis", "postgresql",
    "sqlite", "mongodb", "async", "microservice", "security", "logging",
    "monitoring", "refactor", "pattern", "utility", "helper", "caching",
]

_MAX_ENRICHED_ITEMS = 30
_MAX_CONTENT_CHARS = 1200


def _query_lower(state: GraphState) -> str:
    return str(state.query or "").lower()


def _hits(query: str, keywords: frozenset[str]) -> bool:
    return any(kw in query for kw in keywords)


def _extract_tag_hints(query: str) -> list[str]:
    return [tag for tag in _KNOWN_TAGS if tag in query]


class ContextEnricherNode:
    """Fetch structured store data (skills, memories, errors) when the query
    requests analysis or enumeration of those items.

    The vector retriever only searches ingested code documents.  Skills and
    memories live in a separate table and are never seen by the LLM unless
    explicitly fetched here.  This node detects the intent and populates
    ``state.metadata["enriched_context"]`` before the reasoning node builds
    the LLM prompt.
    """

    def __init__(self, store: IOperationalStore) -> None:
        self._store = store

    async def run(self, state: GraphState) -> GraphState:
        query = _query_lower(state)

        wants_skills = _hits(query, _SKILL_NOUNS)
        wants_memories = _hits(query, _MEMORY_NOUNS)
        wants_errors = _hits(query, _ERROR_NOUNS)

        # An explicit data-type noun is required — analysis verbs alone are not enough
        # to avoid false positives on general questions (e.g. "what is X?").
        if not (wants_skills or wants_memories or wants_errors):
            return state

        tag_hints = _extract_tag_hints(query)
        enriched: list[dict[str, Any]] = []

        if wants_skills:
            enriched += await self._fetch_skills(state, tag_hints)

        if wants_memories:
            enriched += await self._fetch_memories(state, tag_hints)

        if wants_errors:
            enriched += await self._fetch_errors()

        if enriched:
            state.metadata["enriched_context"] = enriched
            logger.debug(
                "ContextEnricher: %d items fetched for query %r",
                len(enriched),
                state.query[:80],
            )

        return state

    async def _fetch_skills(
        self, state: GraphState, tag_hints: list[str]
    ) -> list[dict[str, Any]]:
        try:
            items = await self._store.list_skills_by_kind(
                is_memory=False,
                owner_id=state.user_id,
            )
        except Exception as exc:
            logger.debug("ContextEnricher.list_skills failed: %s", exc)
            return []
        return _format_items(items, tag_hints, item_type="skill")

    async def _fetch_memories(
        self, state: GraphState, tag_hints: list[str]
    ) -> list[dict[str, Any]]:
        try:
            items = await self._store.list_skills_by_kind(
                is_memory=True,
                owner_id=state.user_id,
            )
        except Exception as exc:
            logger.debug("ContextEnricher.list_memories failed: %s", exc)
            return []
        return _format_items(items, tag_hints, item_type="memory")

    async def _fetch_errors(self) -> list[dict[str, Any]]:
        try:
            errors = await self._store.list_errors()
        except Exception as exc:
            logger.debug("ContextEnricher.list_errors failed: %s", exc)
            return []
        return [
            {
                "type": "error",
                "title": str(getattr(e, "error_code", "") or ""),
                "content": str(getattr(e, "error_message", "") or ""),
                "tags": [],
                "quality_score": 0.0,
                "language": "",
            }
            for e in errors[:_MAX_ENRICHED_ITEMS]
        ]


def _relevance(item: Any, tag_hints: list[str]) -> float:
    tags = [t.lower() for t in (getattr(item, "tags", None) or [])]
    tag_score = sum(1.5 for hint in tag_hints if hint in tags)
    return tag_score + float(getattr(item, "quality_score", 0) or 0)


def _format_items(
    items: list[Any], tag_hints: list[str], *, item_type: str
) -> list[dict[str, Any]]:
    scored = sorted(items, key=lambda it: _relevance(it, tag_hints), reverse=True)

    # When tag hints given, prefer tag-matching items; fall back to all
    if tag_hints:
        matched = [
            it for it in scored
            if any(
                h in [t.lower() for t in (getattr(it, "tags", None) or [])]
                for h in tag_hints
            )
        ]
        pool = matched if matched else scored
    else:
        pool = scored

    return [
        {
            "type": item_type,
            "title": str(getattr(item, "title", "") or ""),
            "content": str(getattr(item, "content", "") or "")[:_MAX_CONTENT_CHARS],
            "tags": list(getattr(item, "tags", None) or []),
            "quality_score": float(getattr(item, "quality_score", 0) or 0),
            "language": str(getattr(item, "language", "") or ""),
        }
        for item in pool[:_MAX_ENRICHED_ITEMS]
    ]
