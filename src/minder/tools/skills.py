from __future__ import annotations

import json
import math
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from collections.abc import Awaitable, Callable

from minder.continuity import compatibility_score_for_memory, step_keywords
from minder.config import MinderConfig
from minder.embedding.local import LocalEmbeddingProvider
from minder.observability.metrics import record_continuity_skill_recall
from minder.store.interfaces import IOperationalStore


@dataclass(frozen=True)
class _ImportTarget:
    source_path: str
    files: tuple[Path, ...]


class SkillTools:
    _ALLOWED_EXCERPT_KINDS = {"none", "reusable_excerpt"}
    _IMPORT_SUFFIXES = {".json", ".md", ".markdown", ".txt"}
    _CANONICAL_SKILL_FILENAMES = {
        "skill.md",
        "skill.markdown",
        "skill.txt",
    }
    _DEFAULT_IMPORT_SOURCE_PATH = "skills"
    _AUTO_IMPORT_SOURCE_PATH = "auto"
    _DISCOVERY_DIRECTORY_NAMES = {
        "skill",
        "skills",
        "skill-pack",
        "skill-packs",
        "skill_pack",
        "skill_packs",
        "skillpacks",
        "playbook",
        "playbooks",
        "runbook",
        "runbooks",
        "checklists",
    }
    _DISCOVERY_FILE_HINTS = ("skill", "playbook", "runbook", "checklist")
    _PRUNED_IMPORT_NAMES = {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "coverage",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
    }
    _ALLOWED_HIDDEN_IMPORT_DIRS = {".agents", ".minder"}
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
        source_metadata: dict[str, Any] | None = None,
        excerpt_kind: str = "none",
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
            source_metadata=self._normalized_source_metadata(source_metadata),
            excerpt_kind=self._validated_excerpt_kind(excerpt_kind),
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
        source_metadata: dict[str, Any] | None = None,
        excerpt_kind: str | None = None,
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
        if source_metadata is not None:
            update_data["source_metadata"] = self._normalized_source_metadata(
                source_metadata
            )
        if excerpt_kind is not None:
            update_data["excerpt_kind"] = self._validated_excerpt_kind(excerpt_kind)
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

    async def minder_skill_import_git(
        self,
        *,
        repo_url: str,
        source_path: str = "skills",
        ref: str | None = None,
        provider: str | None = None,
        excerpt_kind: str = "none",
        progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        normalized_repo_url = self._normalize_repo_url(repo_url)
        normalized_source_path = self._normalize_source_path(source_path)
        resolved_provider = self._resolve_provider(provider, normalized_repo_url)
        validated_excerpt_kind = self._validated_excerpt_kind(excerpt_kind)

        async def emit_progress(**payload: Any) -> None:
            if progress_callback is None:
                return
            await progress_callback(payload)

        with tempfile.TemporaryDirectory(prefix="minder-skill-import-") as tmp_dir:
            await emit_progress(
                event_type="clone_started",
                message="Cloning Git repository",
            )
            command = ["git", "clone", "--depth", "1"]
            if ref:
                command += ["--branch", ref]
            command += [repo_url, tmp_dir]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                message = (
                    result.stderr.strip() or result.stdout.strip() or "git clone failed"
                )
                raise ValueError(message)

            repo_root = Path(tmp_dir)
            import_targets = self._resolve_import_targets(
                repo_root=repo_root,
                source_path=normalized_source_path,
            )
            await emit_progress(
                event_type="discovery_completed",
                message="Resolved import targets",
                details={
                    "resolved_paths": [target.source_path for target in import_targets],
                },
            )

            existing_by_source_key = self._skills_by_source_key(
                await self._store.list_skills()
            )
            imported: list[dict[str, Any]] = []
            created_count = 0
            updated_count = 0
            imported_file_paths: set[str] = set()
            total_files = sum(len(target.files) for target in import_targets)
            processed_files = 0

            for target in import_targets:
                for file_path in target.files:
                    relative_file_path = file_path.relative_to(repo_root).as_posix()
                    if relative_file_path in imported_file_paths:
                        continue
                    imported_file_paths.add(relative_file_path)
                    processed_files += 1
                    await emit_progress(
                        event_type="file_processing",
                        message=f"Processing {relative_file_path}",
                        progress_current=processed_files,
                        progress_total=total_files,
                        details={
                            "resolved_path": target.source_path,
                            "file_path": relative_file_path,
                        },
                    )
                    documents = self._load_import_documents(file_path)
                    for index, document in enumerate(documents):
                        auxiliary_paths = self._collect_auxiliary_paths(
                            repo_root=repo_root,
                            file_path=file_path,
                        )
                        source_metadata = self._build_import_source_metadata(
                            provider=resolved_provider,
                            repo_url=normalized_repo_url,
                            ref=ref,
                            source_path=target.source_path,
                            file_path=relative_file_path,
                            document_index=index,
                            auxiliary_paths=auxiliary_paths,
                        )
                        source_key = str(source_metadata["import_key"])
                        existing = existing_by_source_key.get(source_key)
                        next_excerpt_kind = document.get(
                            "excerpt_kind", validated_excerpt_kind
                        )
                        if existing is None:
                            stored = await self.minder_skill_store(
                                title=document["title"],
                                content=document["content"],
                                language=document["language"],
                                tags=document["tags"],
                                workflow_steps=document["workflow_steps"],
                                artifact_types=document["artifact_types"],
                                provenance=document["provenance"],
                                quality_score=document["quality_score"],
                                source_metadata=source_metadata,
                                excerpt_kind=next_excerpt_kind,
                            )
                            created_count += 1
                            imported.append(
                                {
                                    "action": "created",
                                    "id": stored["id"],
                                    "title": stored["title"],
                                    "source": stored["source"],
                                }
                            )
                            existing_by_source_key[source_key] = stored
                            continue

                        updated = await self.minder_skill_update(
                            str(existing["id"]),
                            title=document["title"],
                            content=document["content"],
                            language=document["language"],
                            tags=document["tags"],
                            workflow_steps=document["workflow_steps"],
                            artifact_types=document["artifact_types"],
                            provenance=document["provenance"],
                            quality_score=document["quality_score"],
                            source_metadata=source_metadata,
                            excerpt_kind=next_excerpt_kind,
                        )
                        updated_count += 1
                        imported.append(
                            {
                                "action": "updated",
                                "id": updated["id"],
                                "title": updated["title"],
                                "source": updated["source"],
                            }
                        )
                        existing_by_source_key[source_key] = updated

        return {
            "provider": resolved_provider,
            "repo_url": normalized_repo_url,
            "ref": ref,
            "path": normalized_source_path,
            "resolved_paths": [target.source_path for target in import_targets],
            "created_count": created_count,
            "updated_count": updated_count,
            "imported_count": created_count + updated_count,
            "imported": imported,
        }

    async def minder_skill_delete(self, skill_id: str) -> dict[str, bool]:
        await self._store.delete_skill(uuid.UUID(skill_id))
        return {"deleted": True}

    def _serialize_skill(self, skill: Any) -> dict[str, Any]:
        tags = list(getattr(skill, "tags", []) or [])
        source_metadata = self._normalized_source_metadata(
            getattr(skill, "source_metadata", None)
        )
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
            "source": source_metadata,
            "excerpt_kind": self._validated_excerpt_kind(
                str(getattr(skill, "excerpt_kind", "none") or "none")
            ),
        }

    @classmethod
    def _validated_excerpt_kind(cls, excerpt_kind: str) -> str:
        normalized = str(excerpt_kind or "none").strip().lower() or "none"
        if normalized not in cls._ALLOWED_EXCERPT_KINDS:
            raise ValueError(f"Unsupported excerpt_kind: {excerpt_kind}")
        return normalized

    @staticmethod
    def _normalized_source_metadata(
        source_metadata: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(source_metadata, dict) or not source_metadata:
            return None
        normalized = {
            str(key): value
            for key, value in source_metadata.items()
            if value is not None and str(key).strip()
        }
        return normalized or None

    @staticmethod
    def _normalize_source_path(source_path: str) -> str:
        normalized = str(source_path or "skills").strip().strip("/")
        if not normalized:
            return "skills"
        if normalized.lower() == SkillTools._AUTO_IMPORT_SOURCE_PATH:
            return SkillTools._AUTO_IMPORT_SOURCE_PATH
        if Path(normalized).is_absolute() or ".." in Path(normalized).parts:
            raise ValueError(f"Invalid skill source path: {source_path}")
        return normalized

    @classmethod
    def _resolve_import_targets(
        cls,
        *,
        repo_root: Path,
        source_path: str,
    ) -> list[_ImportTarget]:
        auto_discovery = source_path in {
            cls._DEFAULT_IMPORT_SOURCE_PATH,
            cls._AUTO_IMPORT_SOURCE_PATH,
        }
        targets: list[_ImportTarget] = []
        seen_paths: set[str] = set()

        def add_target(candidate: Path) -> None:
            target = cls._build_import_target(repo_root=repo_root, candidate=candidate)
            if target is None or target.source_path in seen_paths:
                return
            target_parts = Path(target.source_path).parts
            for existing in targets:
                existing_parts = Path(existing.source_path).parts
                if target_parts[: len(existing_parts)] == existing_parts:
                    return
            filtered_targets = [
                existing
                for existing in targets
                if Path(existing.source_path).parts[: len(target_parts)] != target_parts
            ]
            if len(filtered_targets) != len(targets):
                targets[:] = filtered_targets
                seen_paths.clear()
                seen_paths.update(existing.source_path for existing in targets)
            seen_paths.add(target.source_path)
            targets.append(target)

        if source_path != cls._AUTO_IMPORT_SOURCE_PATH:
            requested_path = repo_root / source_path
            if requested_path.exists():
                add_target(requested_path)
                if not auto_discovery:
                    return targets
            elif not auto_discovery:
                raise ValueError(
                    f"Skill source path not found in repository: {source_path}"
                )

        if auto_discovery:
            for candidate in cls._discover_skill_candidates(repo_root):
                add_target(candidate)
            if targets:
                return targets
            raise ValueError(
                f"Skill source path not found in repository: {source_path}. "
                "Auto-discovery could not find any supported skill documents."
            )

        raise ValueError(f"No supported skill documents found under {source_path}")

    @classmethod
    def _build_import_target(
        cls,
        *,
        repo_root: Path,
        candidate: Path,
    ) -> _ImportTarget | None:
        try:
            relative_candidate = candidate.relative_to(repo_root)
        except ValueError:
            return None
        if cls._should_ignore_relative_parts(relative_candidate.parts):
            return None
        if candidate.is_file():
            if not cls._is_supported_import_file(candidate):
                return None
            return _ImportTarget(
                source_path=relative_candidate.as_posix(),
                files=(candidate,),
            )
        if not candidate.is_dir():
            return None
        files = tuple(cls._collect_import_files(candidate, repo_root=repo_root))
        if not files:
            return None
        return _ImportTarget(
            source_path=relative_candidate.as_posix(),
            files=files,
        )

    @classmethod
    def _collect_import_files(cls, root: Path, *, repo_root: Path) -> list[Path]:
        canonical_root_file = cls._canonical_skill_file_for_dir(root)
        if canonical_root_file is not None:
            return [canonical_root_file]
        return [
            path
            for path in sorted(root.rglob("*"))
            if path.is_file()
            and cls._is_supported_import_file(path)
            and not cls._should_ignore_relative_parts(
                path.relative_to(repo_root).parts,
            )
            and cls._should_import_supported_file(path, repo_root=repo_root)
        ]

    @classmethod
    def _discover_skill_candidates(cls, repo_root: Path) -> list[Path]:
        candidates: list[tuple[int, str, Path]] = []
        for path in repo_root.rglob("*"):
            try:
                relative = path.relative_to(repo_root)
            except ValueError:
                continue
            if cls._should_ignore_relative_parts(relative.parts):
                continue
            name = path.name.lower()
            relative_text = relative.as_posix().lower()
            score = 0
            if path.is_dir():
                if name in cls._DISCOVERY_DIRECTORY_NAMES:
                    score += 5
                if "skill" in name:
                    score += 4
                if any(hint in relative_text for hint in cls._DISCOVERY_FILE_HINTS):
                    score += 1
                if score <= 0:
                    continue
            elif path.is_file():
                if not cls._is_supported_import_file(path):
                    continue
                if not cls._should_import_supported_file(path, repo_root=repo_root):
                    continue
                if any(hint in name for hint in cls._DISCOVERY_FILE_HINTS):
                    score += 4
                if "skills" in relative_text:
                    score += 2
                if score <= 0:
                    continue
            else:
                continue
            candidates.append((score, relative.as_posix(), path))

        candidates.sort(key=lambda item: (-item[0], item[1]))
        return [path for _, _, path in candidates]

    @classmethod
    def _is_supported_import_file(cls, path: Path) -> bool:
        return path.suffix.lower() in cls._IMPORT_SUFFIXES

    @classmethod
    def _canonical_skill_file_for_dir(cls, directory: Path) -> Path | None:
        for path in sorted(directory.iterdir() if directory.exists() else []):
            if not path.is_file() or not cls._is_supported_import_file(path):
                continue
            if path.name.casefold() in cls._CANONICAL_SKILL_FILENAMES:
                return path
        return None

    @classmethod
    def _canonical_skill_ancestor_file(
        cls,
        *,
        path: Path,
        repo_root: Path,
    ) -> Path | None:
        current = path.parent
        while current != repo_root and repo_root in current.parents:
            canonical = cls._canonical_skill_file_for_dir(current)
            if canonical is not None:
                return canonical
            current = current.parent
        canonical = cls._canonical_skill_file_for_dir(repo_root)
        if canonical is not None:
            return canonical
        return None

    @classmethod
    def _should_import_supported_file(cls, path: Path, *, repo_root: Path) -> bool:
        canonical_ancestor = cls._canonical_skill_ancestor_file(
            path=path,
            repo_root=repo_root,
        )
        if canonical_ancestor is None:
            return True
        return canonical_ancestor == path

    @classmethod
    def _collect_auxiliary_paths(
        cls,
        *,
        repo_root: Path,
        file_path: Path,
    ) -> list[str]:
        skill_root = file_path.parent
        canonical = cls._canonical_skill_file_for_dir(skill_root)
        if canonical is None or canonical != file_path:
            return []
        auxiliary_paths: list[str] = []
        for candidate in sorted(skill_root.rglob("*")):
            if candidate == canonical:
                continue
            if cls._should_ignore_relative_parts(
                candidate.relative_to(repo_root).parts
            ):
                continue
            if candidate.is_file() and not cls._is_supported_import_file(candidate):
                auxiliary_paths.append(candidate.relative_to(skill_root).as_posix())
                continue
            if candidate.is_file():
                auxiliary_paths.append(candidate.relative_to(skill_root).as_posix())
                continue
            if candidate.is_dir() and candidate != skill_root:
                auxiliary_paths.append(candidate.relative_to(skill_root).as_posix())
        return auxiliary_paths

    @classmethod
    def _should_ignore_relative_parts(cls, parts: tuple[str, ...]) -> bool:
        for part in parts:
            if part in cls._PRUNED_IMPORT_NAMES:
                return True
            if part.startswith(".") and part not in cls._ALLOWED_HIDDEN_IMPORT_DIRS:
                return True
        return False

    @staticmethod
    def _normalize_repo_url(repo_url: str) -> str:
        raw = str(repo_url or "").strip()
        if not raw:
            raise ValueError("repo_url is required")
        parsed = urlparse(raw)
        if parsed.scheme or raw.startswith("git@"):
            return raw.rstrip("/")
        path = Path(raw).expanduser()
        if path.exists():
            return path.resolve().as_posix()
        return raw.rstrip("/")

    @staticmethod
    def _resolve_provider(provider: str | None, repo_url: str) -> str:
        if provider:
            normalized = str(provider).strip().lower()
            if normalized in {"github", "gitlab", "generic_git"}:
                return normalized
            raise ValueError(f"Unsupported provider: {provider}")
        lowered = repo_url.lower()
        if "github.com" in lowered:
            return "github"
        if "gitlab" in lowered:
            return "gitlab"
        return "generic_git"

    def _skills_by_source_key(self, skills: list[Any]) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for skill in skills:
            serialized = self._serialize_skill(skill)
            source = serialized.get("source") or {}
            source_key = str(source.get("import_key") or "").strip()
            if source_key:
                indexed[source_key] = serialized
        return indexed

    def _build_import_source_metadata(
        self,
        *,
        provider: str,
        repo_url: str,
        ref: str | None,
        source_path: str,
        file_path: str,
        document_index: int,
        auxiliary_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        import_key = "::".join(
            [
                provider,
                repo_url,
                ref or "HEAD",
                source_path,
                file_path,
                str(document_index),
            ]
        )
        return {
            "provider": provider,
            "repo_url": repo_url,
            "ref": ref,
            "path": source_path,
            "file_path": file_path,
            "auxiliary_paths": list(auxiliary_paths or []),
            "import_key": import_key,
            "imported_at": datetime.now(UTC).isoformat(),
        }

    def _load_import_documents(self, file_path: Path) -> list[dict[str, Any]]:
        suffix = file_path.suffix.lower()
        raw = file_path.read_text(encoding="utf-8")
        if suffix in {".md", ".markdown", ".txt"}:
            title = self._extract_document_title(raw, fallback=file_path.stem)
            return [
                {
                    "title": title,
                    "content": raw.strip(),
                    "language": "markdown" if suffix != ".txt" else "text",
                    "tags": [],
                    "workflow_steps": [],
                    "artifact_types": [],
                    "provenance": None,
                    "quality_score": 0.0,
                }
            ]
        if suffix == ".json":
            payload = json.loads(raw)
            if isinstance(payload, dict) and isinstance(payload.get("skills"), list):
                candidates = payload.get("skills") or []
            elif isinstance(payload, list):
                candidates = payload
            else:
                candidates = [payload]
            documents = [
                self._coerce_import_document(item, file_path=file_path)
                for item in candidates
            ]
            return [document for document in documents if document is not None]
        raise ValueError(f"Unsupported skill import file: {file_path.name}")

    def _coerce_import_document(
        self,
        payload: Any,
        *,
        file_path: Path,
    ) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        content = str(payload.get("content", "") or "").strip()
        title = str(payload.get("title", "") or "").strip() or file_path.stem
        if not content:
            return None
        return {
            "title": title,
            "content": content,
            "language": str(payload.get("language", "markdown") or "markdown"),
            "tags": [str(tag) for tag in list(payload.get("tags", []) or [])],
            "workflow_steps": [
                str(step) for step in list(payload.get("workflow_steps", []) or [])
            ],
            "artifact_types": [
                str(item) for item in list(payload.get("artifact_types", []) or [])
            ],
            "provenance": (
                str(payload.get("provenance"))
                if payload.get("provenance") is not None
                else None
            ),
            "quality_score": float(payload.get("quality_score", 0.0) or 0.0),
            "excerpt_kind": (
                str(payload.get("excerpt_kind"))
                if payload.get("excerpt_kind") is not None
                else "none"
            ),
        }

    @staticmethod
    def _extract_document_title(raw: str, *, fallback: str) -> str:
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip() or fallback
        return fallback

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
