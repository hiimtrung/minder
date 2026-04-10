from __future__ import annotations

import math
import uuid
from typing import Any

from minder.config import MinderConfig
from minder.embedding.local import LocalEmbeddingProvider
from minder.store.interfaces import IOperationalStore


class MemoryTools:
    def __init__(self, store: IOperationalStore, config: MinderConfig) -> None:
        self._store = store
        self._embedder = LocalEmbeddingProvider(
            config.embedding.model_path,
            dimensions=min(config.embedding.dimensions, 16),
            runtime="auto",
        )

    async def minder_memory_store(
        self,
        *,
        title: str,
        content: str,
        tags: list[str],
        language: str,
    ) -> dict[str, Any]:
        skill = await self._store.create_skill(
            id=uuid.uuid4(),
            title=title,
            content=content,
            language=language,
            tags=tags,
            embedding=self._embedder.embed(f"{title}\n{content}"),
            usage_count=0,
            quality_score=0.0,
        )
        return {"id": str(skill.id), "title": skill.title, "tags": list(skill.tags)}

    async def minder_memory_recall(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        query_embedding = self._embedder.embed(query)
        skills = await self._store.list_skills()
        ranked: list[dict[str, Any]] = []
        for skill in skills:
            embedding = skill.embedding if isinstance(skill.embedding, list) else None
            if not embedding:
                continue
            score = self._cosine_similarity(query_embedding, embedding)
            ranked.append(
                {
                    "id": str(skill.id),
                    "title": skill.title,
                    "content": skill.content,
                    "tags": list(skill.tags) if isinstance(skill.tags, list) else [],
                    "score": round(score, 4),
                }
            )
        ranked.sort(key=lambda item: float(item["score"]), reverse=True)
        return ranked[:limit]

    async def minder_memory_list(self) -> list[dict[str, Any]]:
        skills = await self._store.list_skills()
        return [
            {
                "id": str(skill.id),
                "title": skill.title,
                "language": skill.language,
                "tags": list(skill.tags) if isinstance(skill.tags, list) else [],
            }
            for skill in skills
        ]

    async def minder_memory_delete(self, skill_id: str) -> dict[str, bool]:
        await self._store.delete_skill(uuid.UUID(skill_id))
        return {"deleted": True}

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right, strict=False))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)
