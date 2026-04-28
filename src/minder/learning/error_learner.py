"""P7-T03 — Record error patterns from failed workflow executions."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from minder.store.interfaces import IOperationalStore

if TYPE_CHECKING:
    from minder.graph.state import GraphState

_ERROR_TAG = "error_pattern"
_AUTO_TAG = "auto_synthesized"
_MAX_ERROR_SKILLS = 100


class ErrorLearner:
    """Persists error patterns so future guard/reasoning nodes can avoid them."""

    def __init__(self, store: IOperationalStore, embedder: Any) -> None:
        self._store = store
        self._embedder = embedder

    async def learn(self, state: GraphState) -> dict[str, Any] | None:
        failures = list(state.metadata.get("attempt_failures", []) or [])
        if not failures:
            return None

        existing = await self._store.list_skills()
        error_count = sum(
            1 for s in existing if _ERROR_TAG in (getattr(s, "tags", []) or [])
        )
        if error_count >= _MAX_ERROR_SKILLS:
            return None

        title = f"Error pattern: {state.query[:60]}"
        content = _render_error(state.query, failures)
        embedding = self._embedder.embed(f"{title}\n{content}")

        skill = await self._store.create_skill(
            id=uuid.uuid4(),
            title=title,
            content=content,
            language="markdown",
            tags=[_ERROR_TAG, _AUTO_TAG, "source:auto"],
            embedding=embedding,
            usage_count=0,
            quality_score=0.0,
            source_metadata={"error_source": "workflow_execution"},
            excerpt_kind="none",
        )
        return {"id": str(skill.id), "failure_count": len(failures)}


def _render_error(query: str, failures: list[dict[str, Any]]) -> str:
    lines = [
        "## Error Pattern",
        "",
        f"**Query**: {query}",
        "",
        "**Failure sequence**:",
    ]
    for i, failure in enumerate(failures[:5], 1):
        edge = failure.get("edge", "unknown")
        reason = str(failure.get("reason", ""))[:200]
        provider = failure.get("provider", "unknown")
        lines.append(f"{i}. attempt={failure.get('attempt', i)}, "
                     f"edge={edge}, provider={provider}: {reason}")
    return "\n".join(lines) + "\n"
