from __future__ import annotations

import math
import uuid
from typing import Any

from minder.continuity import compatibility_score_for_memory
from minder.continuity import ContinuitySynthesizer
from minder.config import MinderConfig
from minder.embedding.local import LocalEmbeddingProvider
from minder.observability.metrics import record_continuity_recall
from minder.store.interfaces import IOperationalStore


class MemoryTools:
    def __init__(self, store: IOperationalStore, config: MinderConfig) -> None:
        self._store = store
        self._config = config
        self._embedder = LocalEmbeddingProvider(
            config.embedding.model_path,
            dimensions=min(config.embedding.dimensions, 16),
            runtime="auto",
        )
        self._synthesizer = ContinuitySynthesizer(config)

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

        # Record persistent audit event
        try:
            await self._store.create_audit_log(
                actor_type="system",
                actor_id="minder",
                event_type="skill.created",
                resource_type="skill",
                resource_id=str(skill.id),
                outcome="success",
                audit_metadata={"title": title},
            )
        except Exception:
            pass

        return {"id": str(skill.id), "title": skill.title, "tags": list(skill.tags)}

    async def minder_memory_recall(
        self,
        query: str,
        *,
        limit: int = 5,
        current_step: str | None = None,
        artifact_type: str | None = None,
    ) -> list[dict[str, Any]]:
        query_embedding = self._embedder.embed(query)
        skills = await self._store.list_skills()
        ranked: list[dict[str, Any]] = []
        for skill in skills:
            embedding = skill.embedding if isinstance(skill.embedding, list) else None
            if not embedding:
                continue
            semantic_score = self._cosine_similarity(query_embedding, embedding)
            compatibility_score, compatibility_reasons = compatibility_score_for_memory(
                tags=list(skill.tags) if isinstance(skill.tags, list) else [],
                title=str(skill.title),
                content=str(skill.content),
                current_step=current_step,
                artifact_type=artifact_type,
            )
            score = min((semantic_score * 0.8) + (compatibility_score * 0.2), 1.0)
            ranked.append(
                {
                    "id": str(skill.id),
                    "title": skill.title,
                    "content": skill.content,
                    "tags": list(skill.tags) if isinstance(skill.tags, list) else [],
                    "semantic_score": round(semantic_score, 4),
                    "step_compatibility": round(compatibility_score, 4),
                    "continuity_reasons": compatibility_reasons,
                    "score": round(score, 4),
                }
            )
        ranked.sort(key=lambda item: float(item["score"]), reverse=True)
        limited = ranked[:limit]
        synthesis, synthesis_meta = self._synthesizer.synthesize_memory_hits(
            query=query,
            hits=limited,
            current_step=current_step,
            artifact_type=artifact_type,
        )
        for item in limited:
            item["recall_summary"] = synthesis["summary"]
            item["hit_summary"] = synthesis["hit_summaries"].get(str(item["id"]), "")
            item["synthesis"] = synthesis_meta
            record_continuity_recall(
                provider=str(synthesis_meta.get("provider", "unknown")),
                step_compatibility=float(item["step_compatibility"]),
            )
        return limited

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

        # Record persistent audit event
        try:
            await self._store.create_audit_log(
                actor_type="system",
                actor_id="minder",
                event_type="skill.deleted",
                resource_type="skill",
                resource_id=skill_id,
                outcome="success",
            )
        except Exception:
            pass

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
