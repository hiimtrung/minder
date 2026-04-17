from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping

from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import BaseRoute, Route

from minder.tools.query import QueryTools

from .context import AdminRouteContext

logger = logging.getLogger(__name__)

_PROMPT_LEAK_MARKERS = (
    "Workflow instruction:",
    "Instruction envelope:",
    "Continuity packet:",
    "User query:",
    "Retrieved context:",
    "Correction required:",
)


class RuntimeQueryRequest(BaseModel):
    query: str
    repo_id: str | None = None
    workflow_name: str | None = None
    max_attempts: int = Field(default=2, ge=1, le=4)


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
        query = str(payload.query).strip()
        repo_id = uuid.UUID(str(payload.repo_id)) if payload.repo_id else None

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
                "repository": {
                    "id": (
                        str(repository.get("id") or payload.repo_id)
                        if (repository.get("id") or payload.repo_id)
                        else None
                    ),
                    "name": repository.get("name") if repository else None,
                    "path": repo_path,
                },
                "answer": cleaned_answer,
                "answer_sanitized": answer_sanitized,
                "answer_warning": answer_warning,
            }
        )

    async def runtime_query_stream(request) -> StreamingResponse | JSONResponse:
        resolved = await _resolve_request(request)
        if isinstance(resolved, JSONResponse):
            return resolved
        payload, repository, repo_path = resolved
        query = str(payload.query).strip()
        repo_id = uuid.UUID(str(payload.repo_id)) if payload.repo_id else None

        async def event_stream():
            query_tools = QueryTools(context.store, context.config)
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
