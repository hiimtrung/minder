"""P7-T04 — Update skill quality scores after successful workflow executions."""

from __future__ import annotations

import math
import uuid
from typing import TYPE_CHECKING, Any

from minder.store.interfaces import IOperationalStore

if TYPE_CHECKING:
    from minder.graph.state import GraphState

_EMA_ALPHA = 0.2
_SIMILARITY_THRESHOLD = 0.60
_PATTERN_TAG = "workflow_pattern"


class QualityOptimizer:
    """Blends current quality scores with new evaluation scores using EMA.

    Skills are identified either via explicit `recalled_skill_ids` in
    state.metadata (set by the MCP tool layer) or by embedding similarity
    to the current query when no explicit IDs are provided.
    """

    def __init__(self, store: IOperationalStore, embedder: Any) -> None:
        self._store = store
        self._embedder = embedder

    async def optimize(self, state: GraphState) -> list[dict[str, Any]]:
        new_quality = float((state.evaluation or {}).get("quality_score", 0.0) or 0.0)
        if new_quality <= 0.0:
            return []

        skill_ids = list(state.metadata.get("recalled_skill_ids", []) or [])
        if skill_ids:
            return await self._update_by_ids(skill_ids, new_quality)

        return await self._update_by_similarity(state.query, new_quality)

    async def _update_by_ids(
        self, skill_ids: list[str], new_quality: float
    ) -> list[dict[str, Any]]:
        updated: list[dict[str, Any]] = []
        for sid in skill_ids:
            try:
                skill_id = uuid.UUID(sid)
            except ValueError:
                continue
            skill = await self._store.get_skill_by_id(skill_id)
            if skill is None:
                continue
            result = await self._blend_and_update(skill, new_quality)
            if result:
                updated.append(result)
        return updated

    async def _update_by_similarity(
        self, query: str, new_quality: float
    ) -> list[dict[str, Any]]:
        query_emb = self._embedder.embed(query)
        updated: list[dict[str, Any]] = []
        for skill in await self._store.list_skills():
            tags = list(getattr(skill, "tags", []) or [])
            if _PATTERN_TAG not in tags:
                continue
            emb = skill.embedding if isinstance(skill.embedding, list) else None
            if not emb or _cosine(query_emb, emb) < _SIMILARITY_THRESHOLD:
                continue
            result = await self._blend_and_update(skill, new_quality)
            if result:
                updated.append(result)
        return updated

    async def _blend_and_update(
        self, skill: Any, new_quality: float
    ) -> dict[str, Any] | None:
        skill_id = skill.id
        if isinstance(skill_id, str):
            try:
                skill_id = uuid.UUID(skill_id)
            except ValueError:
                return None

        current_quality = float(getattr(skill, "quality_score", 0.0) or 0.0)
        current_usage = int(getattr(skill, "usage_count", 0) or 0)
        blended = (1 - _EMA_ALPHA) * current_quality + _EMA_ALPHA * new_quality
        await self._store.update_skill(
            skill_id,
            usage_count=current_usage + 1,
            quality_score=round(blended, 4),
        )
        return {"id": str(skill_id), "quality_score": round(blended, 4)}


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return num / (na * nb)
