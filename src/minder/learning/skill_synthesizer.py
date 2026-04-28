"""P7-T02 — Synthesize a new skill from a workflow-execution pattern."""

from __future__ import annotations

import math
import uuid
from typing import Any

from minder.store.interfaces import IOperationalStore


_SYNTHESIS_TAG = "workflow_pattern"
_AUTO_TAG = "auto_synthesized"
_SIMILARITY_THRESHOLD = 0.82


class SkillSynthesizer:
    """Creates a skill from a workflow pattern when no near-duplicate exists."""

    def __init__(
        self,
        store: IOperationalStore,
        embedder: Any,
    ) -> None:
        self._store = store
        self._embedder = embedder

    async def synthesize(self, pattern: dict[str, Any]) -> dict[str, Any] | None:
        title = f"Workflow pattern: {pattern['query'][:80]}"
        content = _render_pattern(pattern)
        embedding = self._embedder.embed(f"{title}\n{content}")

        for skill in await self._store.list_skills():
            tags = list(getattr(skill, "tags", []) or [])
            if _SYNTHESIS_TAG not in tags:
                continue
            existing_emb = (
                skill.embedding if isinstance(skill.embedding, list) else None
            )
            if existing_emb and _cosine(embedding, existing_emb) >= _SIMILARITY_THRESHOLD:
                return None

        skill = await self._store.create_skill(
            id=uuid.uuid4(),
            title=title,
            content=content,
            language="markdown",
            tags=[_SYNTHESIS_TAG, _AUTO_TAG, "source:auto"],
            embedding=embedding,
            usage_count=0,
            quality_score=round(float(pattern.get("quality_score", 0.0) or 0.0), 4),
            source_metadata={"synthesized_from": "workflow_execution"},
            excerpt_kind="reusable_excerpt",
        )
        return {"id": str(skill.id), "title": str(skill.title)}


def _render_pattern(pattern: dict[str, Any]) -> str:
    sources = ", ".join(pattern.get("sources_used", [])[:5]) or "none"
    return (
        f"## Workflow Execution Pattern\n\n"
        f"**Query**: {pattern['query']}\n\n"
        f"**Workflow**: {pattern.get('workflow_name', 'default')} / "
        f"step: {pattern.get('current_step', 'unknown')}\n\n"
        f"**Outcome**: {pattern.get('edge', 'complete')} "
        f"(quality: {pattern.get('quality_score', 0.0):.2f}, "
        f"attempts: {pattern.get('attempt_count', 1)})\n\n"
        f"**Sources used**: {sources}\n\n"
        f"**LLM provider**: {pattern.get('llm_provider', 'unknown')}\n"
    )


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return num / (na * nb)
