from __future__ import annotations

import math
from typing import Any, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from minder.config import MinderConfig
from minder.embedding.local import LocalEmbeddingProvider
from minder.observability.metrics import record_admin_operation
from minder.prompts import PromptRegistry
from minder.tools.memory import MemoryTools
from minder.tools.skills import SkillTools

from .context import AdminRouteContext
from .memories import _serialize_memory
from .prompts import _serialize_prompt


def _config_from_request(request: Request) -> MinderConfig:
    config = getattr(request.app.state, "config", None)
    if isinstance(config, MinderConfig):
        return config
    return MinderConfig()


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in value.lower()
        .replace("/", " ")
        .replace("_", " ")
        .replace("-", " ")
        .split()
        if token
    }


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _lexical_score(query: str, candidate: str) -> float:
    query_lower = query.lower()
    candidate_lower = candidate.lower()
    query_tokens = _tokenize(query)
    candidate_tokens = _tokenize(candidate)
    overlap = 0.0
    if query_tokens:
        overlap = len(query_tokens & candidate_tokens) / max(len(query_tokens), 1)
    contains = 1.0 if query_lower in candidate_lower else 0.0
    prefix = 1.0 if candidate_lower.startswith(query_lower) else 0.0
    return (overlap * 0.6) + (contains * 0.25) + (prefix * 0.15)


def _rank_serialized_items(
    *,
    items: list[dict[str, Any]],
    query: str,
    text_builder: Callable[[dict[str, Any]], str],
    config: MinderConfig,
) -> list[dict[str, Any]]:
    if not query.strip():
        return items

    embedder = LocalEmbeddingProvider(
        config.embedding.model_path,
        dimensions=min(config.embedding.dimensions, 16),
        runtime="auto",
    )
    query_embedding = embedder.embed(query)
    ranked: list[dict[str, Any]] = []
    for item in items:
        candidate_text = text_builder(item).strip()
        if not candidate_text:
            continue
        candidate_embedding = embedder.embed(candidate_text)
        semantic_score = _cosine_similarity(query_embedding, candidate_embedding)
        lexical_score = _lexical_score(query, candidate_text)
        score = (semantic_score * 0.72) + (lexical_score * 0.28)
        next_item = {**item, "search_score": round(score, 4)}
        ranked.append(next_item)
    ranked.sort(
        key=lambda item: (
            -float(item.get("search_score", 0.0) or 0.0),
            str(item.get("title") or item.get("name") or item.get("id") or "").lower(),
        )
    )
    return ranked


def _slice_items(
    items: list[dict[str, Any]],
    *,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    total = len(items)
    return {
        "items": items[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def _prompt_items(context: AdminRouteContext) -> list[dict[str, Any]]:
    prompt_index = {
        prompt.name: prompt for prompt in PromptRegistry.builtin_prompt_models()
    }
    for prompt in await context.store.list_prompts():
        prompt_index[prompt.name] = prompt
    ordered = sorted(
        prompt_index.values(),
        key=lambda prompt: (
            not bool(getattr(prompt, "is_builtin", False)),
            str(getattr(prompt, "name", "")).lower(),
        ),
    )
    return [_serialize_prompt(prompt) for prompt in ordered]


def build_search_routes(context: AdminRouteContext) -> list[BaseRoute]:
    async def admin_catalog_search(request: Request) -> JSONResponse:
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        resource = str(request.path_params.get("resource", "")).strip().lower()
        query = (request.query_params.get("query") or "").strip()
        try:
            limit = max(1, min(int(request.query_params.get("limit", "100")), 200))
            offset = max(0, int(request.query_params.get("offset", "0")))
        except ValueError:
            return JSONResponse({"error": "Invalid limit or offset"}, status_code=400)

        await record_admin_operation(
            operation=f"search_{resource or 'catalog'}",
            outcome="success",
            actor_id="system",
            store=context.store,
        )

        config = _config_from_request(request)

        if resource == "clients":
            items = (await context.use_cases.list_clients())["clients"]
            ranked = _rank_serialized_items(
                items=items,
                query=query,
                text_builder=lambda item: " ".join(
                    [
                        str(item.get("name", "")),
                        str(item.get("slug", "")),
                        str(item.get("description", "")),
                        " ".join(item.get("tool_scopes", [])),
                        " ".join(item.get("repo_scopes", [])),
                        " ".join(item.get("workflow_scopes", [])),
                    ]
                ),
                config=config,
            )
        elif resource == "repositories":
            items = (await context.use_cases.list_repositories())["repositories"]
            ranked = _rank_serialized_items(
                items=items,
                query=query,
                text_builder=lambda item: " ".join(
                    [
                        str(item.get("name", "")),
                        str(item.get("path", "")),
                        str(item.get("remote_url", "")),
                        str(item.get("default_branch", "")),
                        str(item.get("workflow_name", "")),
                        str(item.get("workflow_state", "")),
                        str(item.get("current_step", "")),
                        " ".join(item.get("tracked_branches", [])),
                    ]
                ),
                config=config,
            )
        elif resource == "workflows":
            items = (await context.use_cases.list_workflows())["workflows"]
            ranked = _rank_serialized_items(
                items=items,
                query=query,
                text_builder=lambda item: " ".join(
                    [
                        str(item.get("name", "")),
                        str(item.get("description", "")),
                        str(item.get("enforcement", "")),
                        " ".join(
                            " ".join(
                                [
                                    str(step.get("name", "")),
                                    str(step.get("description", "")),
                                    str(step.get("gate", "")),
                                ]
                            )
                            for step in item.get("steps", [])
                        ),
                    ]
                ),
                config=config,
            )
        elif resource == "prompts":
            items = await _prompt_items(context)
            ranked = _rank_serialized_items(
                items=items,
                query=query,
                text_builder=lambda item: " ".join(
                    [
                        str(item.get("name", "")),
                        str(item.get("title", "")),
                        str(item.get("description", "")),
                        str(item.get("content_template", "")),
                        " ".join(item.get("arguments", [])),
                    ]
                ),
                config=config,
            )
        elif resource == "skills":
            tools = SkillTools(context.store, config)
            all_items = await tools.minder_skill_list()
            ranked = (
                await tools.minder_skill_recall(query, limit=max(len(all_items), 1))
                if query
                else all_items
            )
        elif resource == "memories":
            tools = MemoryTools(context.store, config)
            all_items = [
                _serialize_memory(skill)
                for skill in sorted(
                    await context.store.list_skills(),
                    key=lambda skill: str(getattr(skill, "title", "")).lower(),
                )
            ]
            ranked = (
                await tools.minder_memory_recall(query, limit=max(len(all_items), 1))
                if query
                else all_items
            )
        else:
            return JSONResponse({"error": "Unsupported resource"}, status_code=404)

        payload = _slice_items(ranked, limit=limit, offset=offset)
        payload["resource"] = resource
        payload["query"] = query
        return JSONResponse(payload)

    return [
        Route("/v1/admin/search/{resource}", admin_catalog_search, methods=["GET"]),
    ]
