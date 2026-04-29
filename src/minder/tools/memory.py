from __future__ import annotations

import math
import uuid
from typing import Any, TYPE_CHECKING

from minder.continuity import compatibility_score_for_memory
from minder.config import MinderConfig
from minder.embedding.local import LocalEmbeddingProvider
from minder.observability.metrics import record_continuity_recall
from minder.store.interfaces import IOperationalStore

if TYPE_CHECKING:
    from minder.continuity import ContinuitySynthesizer

MEMORY_LANGUAGES: frozenset[str | None] = frozenset(
    {"markdown", "text", "en", "vi", "", None}
)


def is_memory_record(skill: Any) -> bool:
    return (
        getattr(skill, "language", "") in MEMORY_LANGUAGES
        and getattr(skill, "source_metadata", None) is None
    )


class MemoryTools:
    def __init__(self, store: IOperationalStore, config: MinderConfig) -> None:
        self._store = store
        self._config = config
        self._embedder = LocalEmbeddingProvider(
            fastembed_model=config.embedding.fastembed_model,
            fastembed_cache_dir=config.embedding.fastembed_cache_dir,
            dimensions=config.embedding.dimensions,
            runtime=config.embedding.runtime,
        )
        self._synthesizer: ContinuitySynthesizer | None = None

    def _get_synthesizer(self) -> "ContinuitySynthesizer":
        if self._synthesizer is None:
            from minder.continuity import ContinuitySynthesizer

            self._synthesizer = ContinuitySynthesizer(self._config)
        return self._synthesizer

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
        skip_synthesis: bool = False,
    ) -> list[dict[str, Any]]:
        query_embedding = self._embedder.embed(query)
        skills = await self._store.list_skills()
        ranked: list[dict[str, Any]] = []
        for skill in skills:
            # Differentiation: Memories are human-language records with no import/source metadata.
            if not is_memory_record(skill):
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
            score = min((semantic_score * 0.8) + (compatibility_score * 0.2), 1.0)
            ranked.append(
                {
                    "id": str(skill.id),
                    "title": skill.title,
                    "content": skill.content,
                    "tags": list(skill.tags) if isinstance(skill.tags, list) else [],
                    "language": str(getattr(skill, "language", "") or "markdown"),
                    "score": round(score, 4),
                    # kept internally for record_continuity_recall below
                    "_step_compat": round(compatibility_score, 4),
                }
            )
        ranked.sort(key=lambda item: float(item["score"]), reverse=True)
        limited = ranked[:limit]

        if skip_synthesis:
            for item in limited:
                item.pop("_step_compat", None)
            return limited

        synthesis, synthesis_meta = self._get_synthesizer().synthesize_memory_hits(
            query=query,
            hits=limited,
            current_step=current_step,
            artifact_type=artifact_type,
        )
        for item in limited:
            item["recall_summary"] = synthesis["summary"]
            item["hit_summary"] = synthesis["hit_summaries"].get(str(item["id"]), "")
            record_continuity_recall(
                provider=str(synthesis_meta.get("provider", "unknown")),
                step_compatibility=float(item.get("_step_compat", 0.0)),
            )
            item["step_compatibility"] = item.pop("_step_compat", 0.0)
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
            if is_memory_record(skill)
        ]

    async def minder_memory_update(
        self,
        memory_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        existing = await self._store.get_skill_by_id(uuid.UUID(memory_id))
        if existing is None or not is_memory_record(existing):
            raise ValueError(f"Memory not found: {memory_id}")

        update_data: dict[str, Any] = {}
        next_title = title if title is not None else str(existing.title)
        next_content = content if content is not None else str(existing.content)
        if title is not None:
            update_data["title"] = title
        if content is not None:
            update_data["content"] = content
        if tags is not None:
            update_data["tags"] = [str(t).strip().lower() for t in tags if str(t).strip()]
        if title is not None or content is not None:
            update_data["embedding"] = self._embedder.embed(f"{next_title}\n{next_content}")

        updated = await self._store.update_skill(uuid.UUID(memory_id), **update_data)
        if updated is None:
            raise ValueError(f"Memory not found: {memory_id}")

        try:
            await self._store.create_audit_log(
                actor_type="system",
                actor_id="minder",
                event_type="skill.updated",
                resource_type="skill",
                resource_id=memory_id,
                outcome="success",
                audit_metadata={"changed_fields": list(update_data.keys())},
            )
        except Exception:
            pass

        return {
            "id": str(updated.id),
            "title": str(updated.title),
            "tags": list(updated.tags) if isinstance(updated.tags, list) else [],
            "updated": True,
        }

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

    async def minder_memory_compact(
        self,
        *,
        memory_ids: list[str],
        similarity_threshold: float = 0.92,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        normalized_ids = self._normalize_memory_ids(memory_ids)
        if len(normalized_ids) < 2:
            raise ValueError("At least two memory_ids are required for compaction")

        records = []
        for memory_id in normalized_ids:
            skill = await self._store.get_skill_by_id(uuid.UUID(memory_id))
            if skill is None:
                raise ValueError(f"Memory not found: {memory_id}")
            embedding = self._embedder.embed(
                self._compaction_text(
                    title=str(skill.title),
                    content=str(skill.content),
                )
            )
            records.append(
                {
                    "id": str(skill.id),
                    "title": str(skill.title),
                    "content": str(skill.content),
                    "language": str(getattr(skill, "language", "") or "markdown"),
                    "tags": list(getattr(skill, "tags", []) or []),
                    "embedding": embedding,
                    "usage_count": int(getattr(skill, "usage_count", 0) or 0),
                    "quality_score": float(getattr(skill, "quality_score", 0.0) or 0.0),
                    "created_at": getattr(skill, "created_at", None),
                    "updated_at": getattr(skill, "updated_at", None),
                }
            )

        groups = self._duplicate_groups(records, similarity_threshold)
        plans = [
            self._build_compaction_plan(group) for group in groups if len(group) > 1
        ]
        # Strip full member records — they are noisy and the caller doesn't need them
        slim_plans = [
            {k: v for k, v in plan.items() if k != "members"} for plan in plans
        ]
        result: dict[str, Any] = {
            "dry_run": dry_run,
            "candidate_count": len(records),
            "duplicate_group_count": len(slim_plans),
            "plans": slim_plans,
        }
        if dry_run or not plans:
            result["compacted_count"] = 0
            result["deleted_count"] = 0
            return result

        compacted: list[dict[str, Any]] = []
        deleted_count = 0
        for plan in plans:
            primary_id = str(plan["primary_id"])
            primary = next(item for item in plan["members"] if item["id"] == primary_id)
            merged_tags = sorted(
                {
                    str(tag).strip().lower()
                    for member in plan["members"]
                    for tag in list(member.get("tags", []) or [])
                    if str(tag).strip()
                }
            )
            merged_content = max(
                [str(member.get("content", "") or "") for member in plan["members"]],
                key=len,
            )
            merged_quality = max(
                float(member.get("quality_score", 0.0) or 0.0)
                for member in plan["members"]
            )
            merged_usage = sum(
                int(member.get("usage_count", 0) or 0) for member in plan["members"]
            )
            updated = await self._store.update_skill(
                uuid.UUID(primary_id),
                content=merged_content,
                tags=merged_tags,
                usage_count=merged_usage,
                quality_score=merged_quality,
                embedding=self._embedder.embed(f"{primary['title']}\n{merged_content}"),
            )
            if updated is None:
                raise ValueError(f"Memory not found during compaction: {primary_id}")

            duplicate_ids = [
                str(member["id"])
                for member in plan["members"]
                if str(member["id"]) != primary_id
            ]
            for duplicate_id in duplicate_ids:
                await self._store.delete_skill(uuid.UUID(duplicate_id))
                deleted_count += 1

            try:
                await self._store.create_audit_log(
                    actor_type="system",
                    actor_id="minder",
                    event_type="skill.compacted",
                    resource_type="skill",
                    resource_id=primary_id,
                    outcome="success",
                    audit_metadata={
                        "merged_ids": duplicate_ids,
                        "similarity_threshold": similarity_threshold,
                    },
                )
            except Exception:
                pass

            compacted.append(
                {
                    "primary_id": primary_id,
                    "merged_ids": duplicate_ids,
                    "merged_tags": merged_tags,
                    "usage_count": merged_usage,
                    "quality_score": round(merged_quality, 4),
                }
            )

        result["compacted_count"] = len(compacted)
        result["deleted_count"] = deleted_count
        result["compacted"] = compacted
        result.pop("plans", None)  # plans are only useful for dry_run preview
        return result

    @staticmethod
    def _compaction_text(*, title: str, content: str) -> str:
        normalized_content = str(content or "").strip()
        if normalized_content:
            return normalized_content
        return str(title or "").strip()

    @staticmethod
    def _normalize_memory_ids(memory_ids: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_id in memory_ids:
            value = str(raw_id or "").strip()
            if not value or value in seen:
                continue
            uuid.UUID(value)
            seen.add(value)
            normalized.append(value)
        return normalized

    @staticmethod
    def _duplicate_groups(
        records: list[dict[str, Any]], similarity_threshold: float
    ) -> list[list[dict[str, Any]]]:
        adjacency: dict[str, set[str]] = {
            str(record["id"]): set() for record in records
        }
        record_map = {str(record["id"]): record for record in records}
        for index, left in enumerate(records):
            left_embedding = list(left.get("embedding") or [])
            for right in records[index + 1 :]:
                right_embedding = list(right.get("embedding") or [])
                similarity = MemoryTools._cosine_similarity(
                    left_embedding, right_embedding
                )
                if similarity < similarity_threshold:
                    continue
                left_id = str(left["id"])
                right_id = str(right["id"])
                adjacency[left_id].add(right_id)
                adjacency[right_id].add(left_id)

        groups: list[list[dict[str, Any]]] = []
        visited: set[str] = set()
        for record in records:
            record_id = str(record["id"])
            if record_id in visited:
                continue
            stack = [record_id]
            component: list[dict[str, Any]] = []
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                component.append(record_map[current])
                stack.extend(sorted(adjacency[current] - visited))
            groups.append(component)
        return groups

    def _build_compaction_plan(self, members: list[dict[str, Any]]) -> dict[str, Any]:
        primary = max(members, key=self._primary_sort_key)
        duplicate_ids = [
            str(member["id"])
            for member in members
            if str(member["id"]) != str(primary["id"])
        ]
        return {
            "primary_id": str(primary["id"]),
            "primary_title": str(primary["title"]),
            "duplicate_ids": duplicate_ids,
            "duplicate_titles": [
                str(member["title"])
                for member in members
                if str(member["id"]) != str(primary["id"])
            ],
            "members": members,
        }

    @staticmethod
    def _primary_sort_key(member: dict[str, Any]) -> tuple[float, int, str, str, int]:
        updated_at = member.get("updated_at")
        created_at = member.get("created_at")
        return (
            float(member.get("quality_score", 0.0) or 0.0),
            int(member.get("usage_count", 0) or 0),
            str(updated_at or ""),
            str(created_at or ""),
            len(str(member.get("content", "") or "")),
        )

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
