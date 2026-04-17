from __future__ import annotations

import math
import uuid
from typing import Any

from minder.continuity import compatibility_score_for_memory, step_keywords
from minder.config import MinderConfig
from minder.embedding.local import LocalEmbeddingProvider
from minder.observability.metrics import record_continuity_skill_recall
from minder.store.interfaces import IOperationalStore


class SkillTools:
    _ARTIFACT_TAGS = {
        "problem_statement",
        "acceptance_criteria",
        "analysis_notes",
        "use_cases",
        "test_plan",
        "failing_tests",
        "implementation_notes",
        "changed_files",
        "verification_report",
        "test_results",
        "review_notes",
        "approval_summary",
        "release_notes",
        "rollback_plan",
        "step_notes",
    }

    def __init__(self, store: IOperationalStore, config: MinderConfig) -> None:
        self._store = store
        self._embedder = LocalEmbeddingProvider(
            config.embedding.model_path,
            dimensions=min(config.embedding.dimensions, 16),
            runtime="auto",
        )

    async def minder_skill_store(
        self,
        *,
        title: str,
        content: str,
        language: str,
        tags: list[str] | None = None,
        workflow_steps: list[str] | None = None,
        artifact_types: list[str] | None = None,
        provenance: str | None = None,
        quality_score: float = 0.0,
    ) -> dict[str, Any]:
        skill = await self._store.create_skill(
            id=uuid.uuid4(),
            title=title,
            content=content,
            language=language,
            tags=self._normalized_tags(
                tags=tags,
                workflow_steps=workflow_steps,
                artifact_types=artifact_types,
                provenance=provenance,
            ),
            embedding=self._embedder.embed(f"{title}\n{content}"),
            usage_count=0,
            quality_score=max(float(quality_score), 0.0),
        )
        return self._serialize_skill(skill)

    async def minder_skill_recall(
        self,
        query: str,
        *,
        limit: int = 5,
        current_step: str | None = None,
        artifact_type: str | None = None,
        min_quality_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        query_embedding = self._embedder.embed(query)
        ranked: list[dict[str, Any]] = []
        for skill in await self._store.list_skills():
            quality_score = float(getattr(skill, "quality_score", 0.0) or 0.0)
            if quality_score < min_quality_score:
                continue
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
            blended_score = min(
                (semantic_score * 0.65)
                + (compatibility_score * 0.2)
                + (min(quality_score, 1.0) * 0.15),
                1.5,
            )
            ranked_item = {
                **self._serialize_skill(skill),
                "semantic_score": round(semantic_score, 4),
                "step_compatibility": round(compatibility_score, 4),
                "continuity_reasons": compatibility_reasons,
                "score": round(blended_score, 4),
            }
            ranked.append(ranked_item)
        ranked.sort(key=lambda item: float(item["score"]), reverse=True)
        limited = ranked[:limit]
        for item in limited:
            record_continuity_skill_recall(
                step_compatibility=float(item["step_compatibility"]),
                quality_score=float(item["quality_score"]),
            )
        return limited

    async def minder_skill_list(
        self,
        *,
        current_step: str | None = None,
        tag: str | None = None,
        min_quality_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        required_tags = {
            str(tag).strip().lower()
            for tag in [tag]
            if tag is not None and str(tag).strip()
        }
        if current_step:
            required_tags.update(step_keywords(current_step))
        items: list[dict[str, Any]] = []
        for skill in await self._store.list_skills():
            quality_score = float(getattr(skill, "quality_score", 0.0) or 0.0)
            if quality_score < min_quality_score:
                continue
            normalized_tags = {
                str(item).strip().lower()
                for item in list(getattr(skill, "tags", []) or [])
                if str(item).strip()
            }
            if required_tags and not required_tags <= normalized_tags:
                continue
            items.append(self._serialize_skill(skill))
        items.sort(
            key=lambda item: (-float(item["quality_score"]), str(item["title"]).lower())
        )
        return items

    async def minder_skill_update(
        self,
        skill_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        language: str | None = None,
        tags: list[str] | None = None,
        workflow_steps: list[str] | None = None,
        artifact_types: list[str] | None = None,
        provenance: str | None = None,
        quality_score: float | None = None,
    ) -> dict[str, Any]:
        existing = await self._store.get_skill_by_id(uuid.UUID(skill_id))
        if existing is None:
            raise ValueError(f"Skill not found: {skill_id}")

        update_data: dict[str, Any] = {}
        next_title = title if title is not None else str(existing.title)
        next_content = content if content is not None else str(existing.content)
        if title is not None:
            update_data["title"] = title
        if content is not None:
            update_data["content"] = content
        if language is not None:
            update_data["language"] = language
        if quality_score is not None:
            update_data["quality_score"] = max(float(quality_score), 0.0)
        if any(
            value is not None
            for value in (tags, workflow_steps, artifact_types, provenance)
        ):
            update_data["tags"] = self._normalized_tags(
                tags=(
                    tags
                    if tags is not None
                    else list(getattr(existing, "tags", []) or [])
                ),
                workflow_steps=workflow_steps,
                artifact_types=artifact_types,
                provenance=provenance,
            )
        if title is not None or content is not None:
            update_data["embedding"] = self._embedder.embed(
                f"{next_title}\n{next_content}"
            )
        updated = await self._store.update_skill(uuid.UUID(skill_id), **update_data)
        if updated is None:
            raise ValueError(f"Skill not found: {skill_id}")
        return self._serialize_skill(updated)

    async def minder_skill_delete(self, skill_id: str) -> dict[str, bool]:
        await self._store.delete_skill(uuid.UUID(skill_id))
        return {"deleted": True}

    def _serialize_skill(self, skill: Any) -> dict[str, Any]:
        tags = list(getattr(skill, "tags", []) or [])
        return {
            "id": str(skill.id),
            "title": str(skill.title),
            "content": str(skill.content),
            "language": str(getattr(skill, "language", "")),
            "tags": tags,
            "quality_score": round(
                float(getattr(skill, "quality_score", 0.0) or 0.0), 4
            ),
            "usage_count": int(getattr(skill, "usage_count", 0) or 0),
            "workflow_step_tags": [
                tag for tag in tags if ":" not in tag and tag not in self._ARTIFACT_TAGS
            ],
            "artifact_type_tags": [tag for tag in tags if tag in self._ARTIFACT_TAGS],
            "provenance": next(
                (tag.split(":", 1)[1] for tag in tags if tag.startswith("source:")),
                None,
            ),
        }

    @staticmethod
    def _normalized_tags(
        *,
        tags: list[str] | None,
        workflow_steps: list[str] | None,
        artifact_types: list[str] | None,
        provenance: str | None,
    ) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        def add(value: str) -> None:
            token = str(value or "").strip().lower()
            if not token or token in seen:
                return
            seen.add(token)
            normalized.append(token)

        for tag in tags or []:
            add(tag)
        for step in workflow_steps or []:
            for token in sorted(step_keywords(step)):
                add(token)
        for artifact in artifact_types or []:
            add(artifact)
        if provenance:
            add(f"source:{provenance}")
        return normalized

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
