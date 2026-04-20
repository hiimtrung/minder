from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import BaseRoute, Route

from minder.tools.memory import MemoryTools
from minder.tools.query import QueryTools
from minder.tools.session import SessionTools
from minder.tools.skills import SkillTools

from .context import AdminRouteContext

logger = logging.getLogger(__name__)

_PROMPT_LEAK_MARKERS = (
    "Workflow instruction:",
    "Instruction envelope:",
    "Continuity packet:",
    "Tool capabilities:",
    "Data access policy:",
    "Repository context note:",
    "User query:",
    "Retrieved context:",
    "Correction required:",
)


class RuntimeQueryRequest(BaseModel):
    query: str
    repo_id: str | None = None
    workflow_name: str | None = None
    max_attempts: int = Field(default=2, ge=1, le=4)


_READ_LIST_VERBS = (
    "list",
    "show",
    "view",
    "what",
    "which",
    "liệt kê",
    "liet ke",
    "xem",
    "danh sách",
    "danh sach",
)
_CREATE_VERBS = (
    "create",
    "add",
    "store",
    "save",
    "new",
    "tạo",
    "tao",
    "thêm",
    "them",
    "lưu",
    "luu",
)
_DELETE_VERBS = ("delete", "remove", "xoá", "xóa", "xoa")
_CLEANUP_VERBS = ("cleanup", "clean up", "purge", "dọn", "don")


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def _extract_quoted_field(query: str, aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        pattern = rf"(?:{re.escape(alias)})\s*[:=]?\s*[\"']([^\"']+)[\"']"
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def _extract_uuid(query: str) -> str | None:
    match = re.search(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b",
        query,
    )
    if match:
        return match.group(0)
    return None


def _extract_tags(query: str) -> list[str]:
    raw = _extract_quoted_field(query, ("tags", "tag"))
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _agentic_payload(
    *,
    query: str,
    answer: str,
    repository: dict[str, Any],
    agent_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "query": query,
        "repository": repository,
        "answer": answer,
        "answer_sanitized": False,
        "answer_warning": None,
        "sources": [],
        "workflow": {},
        "guard_result": None,
        "verification_result": None,
        "evaluation": None,
        "provider": "minder",
        "model": "agentic-tool-router",
        "runtime": "internal",
        "orchestration_runtime": "agentic-tool-executor",
        "transition_log": [
            {"edge": "agent_tool_executed", "tool": action.get("tool")}
            for action in agent_actions
        ],
        "edge": "agent_tool_executed",
        "cross_repo_graph": None,
        "agent_actions": agent_actions,
    }


class RuntimeAgentExecutor:
    def __init__(self, context: AdminRouteContext) -> None:
        self._memory_tools = MemoryTools(context.store, context.config)
        self._skill_tools = SkillTools(context.store, context.config)
        self._session_tools = SessionTools(context.store)

    async def execute(
        self,
        *,
        query: str,
        repository: dict[str, Any],
        admin_user_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        normalized = query.lower().strip()
        if not normalized:
            return None

        if "memory" in normalized or "memories" in normalized:
            return await self._execute_memory(query=query, repository=repository)
        if "skill" in normalized or "skills" in normalized:
            return await self._execute_skill(query=query, repository=repository)
        if "session" in normalized or "sessions" in normalized:
            return await self._execute_session(
                query=query,
                repository=repository,
                admin_user_id=admin_user_id,
            )
        return None

    async def _execute_memory(
        self,
        *,
        query: str,
        repository: dict[str, Any],
    ) -> dict[str, Any] | None:
        normalized = query.lower()
        if _contains_any(normalized, _READ_LIST_VERBS):
            memories = await self._memory_tools.minder_memory_list()
            preview = (
                "\n".join(f"- {item['id']}: {item['title']}" for item in memories[:10])
                if memories
                else "- No memories found."
            )
            return _agentic_payload(
                query=query,
                repository=repository,
                answer=f"Listed {len(memories)} memories.\n{preview}",
                agent_actions=[
                    {
                        "tool": "minder_memory_list",
                        "mode": "read",
                        "status": "success",
                        "count": len(memories),
                    }
                ],
            )

        if _contains_any(normalized, _CREATE_VERBS):
            title = _extract_quoted_field(query, ("title", "memory", "memory title"))
            content = _extract_quoted_field(
                query,
                ("content", "body", "note", "memory content"),
            )
            if not title or not content:
                return None
            created = await self._memory_tools.minder_memory_store(
                title=title,
                content=content,
                tags=_extract_tags(query),
                language=_extract_quoted_field(query, ("language",)) or "markdown",
            )
            return _agentic_payload(
                query=query,
                repository=repository,
                answer=f"Created memory '{created['title']}' with id {created['id']}.",
                agent_actions=[
                    {
                        "tool": "minder_memory_store",
                        "mode": "write",
                        "status": "success",
                        "result": created,
                    }
                ],
            )

        if _contains_any(normalized, _DELETE_VERBS):
            memory_id = _extract_uuid(query)
            if not memory_id:
                return None
            deleted = await self._memory_tools.minder_memory_delete(memory_id)
            return _agentic_payload(
                query=query,
                repository=repository,
                answer=(
                    f"Deleted memory {memory_id}."
                    if deleted.get("deleted")
                    else f"Memory {memory_id} was not deleted."
                ),
                agent_actions=[
                    {
                        "tool": "minder_memory_delete",
                        "mode": "write",
                        "status": "success",
                        "result": deleted,
                    }
                ],
            )
        return None

    async def _execute_skill(
        self,
        *,
        query: str,
        repository: dict[str, Any],
    ) -> dict[str, Any] | None:
        normalized = query.lower()
        if _contains_any(normalized, _READ_LIST_VERBS):
            skills = await self._skill_tools.minder_skill_list()
            preview = (
                "\n".join(f"- {item['id']}: {item['title']}" for item in skills[:10])
                if skills
                else "- No skills found."
            )
            return _agentic_payload(
                query=query,
                repository=repository,
                answer=f"Listed {len(skills)} skills.\n{preview}",
                agent_actions=[
                    {
                        "tool": "minder_skill_list",
                        "mode": "read",
                        "status": "success",
                        "count": len(skills),
                    }
                ],
            )

        if _contains_any(normalized, _CREATE_VERBS):
            title = _extract_quoted_field(query, ("title", "skill", "skill title"))
            content = _extract_quoted_field(
                query,
                ("content", "body", "skill content"),
            )
            if not title or not content:
                return None
            created = await self._skill_tools.minder_skill_store(
                title=title,
                content=content,
                language=_extract_quoted_field(query, ("language",)) or "markdown",
                tags=_extract_tags(query),
            )
            return _agentic_payload(
                query=query,
                repository=repository,
                answer=f"Created skill '{created['title']}' with id {created['id']}.",
                agent_actions=[
                    {
                        "tool": "minder_skill_store",
                        "mode": "write",
                        "status": "success",
                        "result": created,
                    }
                ],
            )

        if _contains_any(normalized, _DELETE_VERBS):
            skill_id = _extract_uuid(query)
            if not skill_id:
                return None
            deleted = await self._skill_tools.minder_skill_delete(skill_id)
            return _agentic_payload(
                query=query,
                repository=repository,
                answer=(
                    f"Deleted skill {skill_id}."
                    if deleted.get("deleted")
                    else f"Skill {skill_id} was not deleted."
                ),
                agent_actions=[
                    {
                        "tool": "minder_skill_delete",
                        "mode": "write",
                        "status": "success",
                        "result": deleted,
                    }
                ],
            )
        return None

    async def _execute_session(
        self,
        *,
        query: str,
        repository: dict[str, Any],
        admin_user_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        normalized = query.lower()
        if _contains_any(normalized, _READ_LIST_VERBS):
            sessions = await self._session_tools.minder_session_list(
                user_id=admin_user_id
            )
            items = list(sessions.get("sessions", []) or [])
            preview = (
                "\n".join(
                    f"- {item['session_id']}: {item.get('name') or 'unnamed'}"
                    for item in items[:10]
                )
                if items
                else "- No sessions found."
            )
            return _agentic_payload(
                query=query,
                repository=repository,
                answer=f"Listed {len(items)} sessions.\n{preview}",
                agent_actions=[
                    {
                        "tool": "minder_session_list",
                        "mode": "read",
                        "status": "success",
                        "count": len(items),
                    }
                ],
            )

        if _contains_any(normalized, _CLEANUP_VERBS):
            cleaned = await self._session_tools.minder_session_cleanup(
                user_id=admin_user_id
            )
            return _agentic_payload(
                query=query,
                repository=repository,
                answer=(
                    f"Cleaned up {cleaned.get('deleted_sessions', 0)} expired sessions and "
                    f"{cleaned.get('deleted_history', 0)} history records."
                ),
                agent_actions=[
                    {
                        "tool": "minder_session_cleanup",
                        "mode": "write",
                        "status": "success",
                        "result": cleaned,
                    }
                ],
            )

        if _contains_any(normalized, _CREATE_VERBS):
            name = _extract_quoted_field(query, ("name", "session", "session name"))
            if not name:
                return None
            repo_id_value = repository.get("id")
            created = await self._session_tools.minder_session_create(
                user_id=admin_user_id,
                name=name,
                repo_id=uuid.UUID(str(repo_id_value)) if repo_id_value else None,
                project_context=(
                    {"repository_name": repository.get("name")}
                    if repository.get("name")
                    else None
                ),
            )
            return _agentic_payload(
                query=query,
                repository=repository,
                answer=f"Created session '{created.get('name') or name}' with id {created['session_id']}.",
                agent_actions=[
                    {
                        "tool": "minder_session_create",
                        "mode": "write",
                        "status": "success",
                        "result": created,
                    }
                ],
            )
        return None


def _fallback_answer(query: str, sources: list[dict[str, object]]) -> str:
    source_paths = [
        str(source.get("path", "")).strip()
        for source in sources[:3]
        if isinstance(source, dict) and str(source.get("path", "")).strip()
    ]
    if source_paths:
        return (
            f'The local runtime did not return a clean natural-language answer for "{query}". '
            f"Start by inspecting: {', '.join(source_paths)}."
        )
    return (
        f'The local runtime did not return a clean natural-language answer for "{query}". '
        "Try a narrower question or inspect the transition log for the current reasoning path."
    )


def _sanitize_answer(
    answer: object,
    *,
    query: str,
    sources: list[dict[str, object]],
) -> tuple[str, bool, str | None]:
    text = str(answer or "").strip()
    if not text:
        return (
            _fallback_answer(query, sources),
            True,
            "Empty model response replaced with a runtime summary.",
        )

    marker_hits = sum(text.count(marker) for marker in _PROMPT_LEAK_MARKERS)
    looks_like_prompt_echo = marker_hits >= 2 or text.startswith(
        "Workflow instruction:"
    )

    if not looks_like_prompt_echo:
        return text, False, None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("answer:"):
            candidate = stripped.split(":", 1)[1].strip()
            if candidate:
                return (
                    candidate,
                    True,
                    "Prompt envelope was removed from the visible answer.",
                )

    return (
        _fallback_answer(query, sources),
        True,
        "Prompt envelope leaked into the model output, so the dashboard replaced it with a cleaner summary.",
    )


def build_runtime_routes(context: AdminRouteContext) -> list[BaseRoute]:
    async def _resolve_request(
        request,
    ) -> tuple[RuntimeQueryRequest, Mapping[str, object], str | None] | JSONResponse:
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        try:
            payload = RuntimeQueryRequest(**(await request.json()))
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        query = str(payload.query).strip()
        if not query:
            return JSONResponse({"error": "query is required"}, status_code=400)

        if not payload.repo_id:
            return payload, {}, None

        try:
            repo_id = uuid.UUID(str(payload.repo_id))
        except ValueError:
            return JSONResponse({"error": "Invalid repo_id"}, status_code=400)

        try:
            repository_payload = await context.use_cases.get_repository_detail(repo_id)
        except LookupError:
            return JSONResponse({"error": "Repository not found"}, status_code=404)

        repository = (
            repository_payload.get("repository", {})
            if isinstance(repository_payload, dict)
            else {}
        )
        repo_path = str(repository.get("path", "") or "").strip()
        if not repo_path:
            return JSONResponse(
                {"error": "Repository path is required for runtime query"},
                status_code=400,
            )
        return payload, repository, repo_path

    async def runtime_query(request) -> JSONResponse:
        resolved = await _resolve_request(request)
        if isinstance(resolved, JSONResponse):
            return resolved
        payload, repository, repo_path = resolved
        admin_user = await context.admin_user_from_request(request)
        query = str(payload.query).strip()
        repo_id = uuid.UUID(str(payload.repo_id)) if payload.repo_id else None
        repository_payload = {
            "id": (
                str(repository.get("id") or payload.repo_id)
                if (repository.get("id") or payload.repo_id)
                else None
            ),
            "name": repository.get("name") if repository else None,
            "path": repo_path,
        }

        agentic_result = await RuntimeAgentExecutor(context).execute(
            query=query,
            repository=repository_payload,
            admin_user_id=admin_user.id,
        )
        if agentic_result is not None:
            return JSONResponse(agentic_result)

        try:
            result = await QueryTools(context.store, context.config).minder_query(
                query=query,
                repo_path=repo_path,
                repo_id=repo_id,
                workflow_name=payload.workflow_name,
                max_attempts=payload.max_attempts,
            )
        except Exception as exc:
            logger.exception("Runtime query failed", exc_info=exc)
            return JSONResponse({"error": str(exc)}, status_code=400)

        sources = list(result.get("sources", []) or [])
        cleaned_answer, answer_sanitized, answer_warning = _sanitize_answer(
            result.get("answer", ""),
            query=query,
            sources=sources,
        )

        return JSONResponse(
            {
                **result,
                "query": query,
                "repository": repository_payload,
                "answer": cleaned_answer,
                "answer_sanitized": answer_sanitized,
                "answer_warning": answer_warning,
                "agent_actions": [],
            }
        )

    async def runtime_query_stream(request) -> StreamingResponse | JSONResponse:
        resolved = await _resolve_request(request)
        if isinstance(resolved, JSONResponse):
            return resolved
        payload, repository, repo_path = resolved
        admin_user = await context.admin_user_from_request(request)
        query = str(payload.query).strip()
        repo_id = uuid.UUID(str(payload.repo_id)) if payload.repo_id else None

        async def event_stream():
            repository_payload = {
                "id": (
                    str(repository.get("id") or payload.repo_id)
                    if (repository.get("id") or payload.repo_id)
                    else None
                ),
                "name": repository.get("name") if repository else None,
                "path": repo_path,
            }
            yield json.dumps({"type": "meta", "repository": repository_payload}) + "\n"
            agentic_result = await RuntimeAgentExecutor(context).execute(
                query=query,
                repository=repository_payload,
                admin_user_id=admin_user.id,
            )
            if agentic_result is not None:
                yield json.dumps({"type": "final", "payload": agentic_result}) + "\n"
                return

            query_tools = QueryTools(context.store, context.config)
            try:
                async for event in query_tools.minder_query_stream(
                    query=query,
                    repo_path=repo_path,
                    repo_id=repo_id,
                    workflow_name=payload.workflow_name,
                    max_attempts=payload.max_attempts,
                ):
                    event_type = str(event.get("type"))
                    if event_type == "final":
                        payload_result = dict(event.get("payload", {}) or {})
                        sources = list(payload_result.get("sources", []) or [])
                        cleaned_answer, answer_sanitized, answer_warning = (
                            _sanitize_answer(
                                payload_result.get("answer", ""),
                                query=query,
                                sources=sources,
                            )
                        )
                        yield json.dumps(
                            {
                                "type": "final",
                                "payload": {
                                    **payload_result,
                                    "query": query,
                                    "repository": repository_payload,
                                    "answer": cleaned_answer,
                                    "answer_sanitized": answer_sanitized,
                                    "answer_warning": answer_warning,
                                    "agent_actions": [],
                                },
                            }
                        ) + "\n"
                        continue
                    yield json.dumps(event) + "\n"
            except Exception as exc:
                logger.exception("Runtime query stream failed", exc_info=exc)
                yield json.dumps({"type": "error", "error": str(exc)}) + "\n"

        return StreamingResponse(
            event_stream(),
            media_type="application/x-ndjson",
        )

    return [
        Route("/api/v1/runtime/query", runtime_query, methods=["POST"]),
        Route("/api/v1/runtime/query/stream", runtime_query_stream, methods=["POST"]),
    ]
