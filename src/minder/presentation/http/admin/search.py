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
    items: list[Any],
    query: str,
    text_builder: Callable[[Any], str],
    config: MinderConfig,
) -> list[Any]:
    if not query.strip():
        return items

    embedder = LocalEmbeddingProvider(
        ollama_url=config.embedding.ollama_url,
        ollama_model=config.embedding.ollama_model,
        dimensions=min(config.embedding.dimensions, 16),
        runtime="auto",
    )
    query_embedding = embedder.embed(query)
    ranked: list[Any] = []
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


def _rank_skill_items(
    *,
    items: list[dict[str, Any]],
    query: str,
    config: MinderConfig,
) -> list[dict[str, Any]]:
    if not query.strip():
        return items

    embedder = LocalEmbeddingProvider(
        ollama_url=config.embedding.ollama_url,
        ollama_model=config.embedding.ollama_model,
        dimensions=min(config.embedding.dimensions, 16),
        runtime="auto",
    )
    query_embedding = embedder.embed(query)
    query_lower = query.strip().lower()
    query_tokens = _tokenize(query)
    ranked: list[dict[str, Any]] = []

    for item in items:
        title = str(item.get("title", "") or "")
        language = str(item.get("language", "") or "")
        tags = [str(tag) for tag in list(item.get("tags", []) or [])]
        candidate_text = " ".join(
            [
                title,
                language,
                " ".join(tags),
                " ".join(item.get("workflow_step_tags", [])),
                " ".join(item.get("artifact_type_tags", [])),
                str(item.get("content", "") or ""),
            ]
        ).strip()
        if not candidate_text:
            continue
        semantic_score = _cosine_similarity(
            query_embedding,
            embedder.embed(candidate_text),
        )
        lexical_score = _lexical_score(query, candidate_text)
        title_lower = title.lower()
        language_lower = language.lower()
        tag_tokens = {tag.lower() for tag in tags}
        exact_boost = 0.0
        if title_lower == query_lower:
            exact_boost += 2.2
        if language_lower == query_lower:
            exact_boost += 2.8
        if query_lower in tag_tokens:
            exact_boost += 1.9
        if title_lower.startswith(query_lower):
            exact_boost += 0.8
        if any(token == language_lower for token in query_tokens):
            exact_boost += 1.4
        if any(token in tag_tokens for token in query_tokens):
            exact_boost += 0.8
        score = (
            (lexical_score * 0.62)
            + (semantic_score * 0.18)
            + exact_boost
            + (min(float(item.get("quality_score", 0.0) or 0.0), 1.0) * 0.05)
        )
        ranked.append(
            {
                **item,
                "search_score": round(score, 4),
                "lexical_score": round(lexical_score, 4),
                "semantic_score": round(semantic_score, 4),
                "exact_match_score": round(exact_boost, 4),
            }
        )

    if (
        query_tokens
        and len(query_tokens) <= 2
        and any(
            float(item.get("exact_match_score", 0.0) or 0.0) > 0
            or float(item.get("lexical_score", 0.0) or 0.0) >= 0.45
            for item in ranked
        )
    ):
        ranked = [
            item
            for item in ranked
            if float(item.get("exact_match_score", 0.0) or 0.0) > 0
            or float(item.get("lexical_score", 0.0) or 0.0) > 0
        ]

    ranked.sort(
        key=lambda item: (
            -float(item.get("search_score", 0.0) or 0.0),
            -float(item.get("exact_match_score", 0.0) or 0.0),
            str(item.get("title") or "").lower(),
        )
    )
    return ranked


def _slice_items(
    items: list[Any],
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

        ranked: list[Any] = []

        if resource == "clients":
            client_items = (await context.use_cases.list_clients())["clients"]
            ranked = _rank_serialized_items(
                items=client_items,
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
            repo_items = (await context.use_cases.list_repositories())["repositories"]
            ranked = _rank_serialized_items(
                items=repo_items,
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
            workflow_items = (await context.use_cases.list_workflows())["workflows"]
            ranked = _rank_serialized_items(
                items=workflow_items,
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
            prompt_items = await _prompt_items(context)
            ranked = _rank_serialized_items(
                items=prompt_items,
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
            skill_tools = SkillTools(context.store, config)
            all_skill_items = await skill_tools.minder_skill_list()
            ranked = _rank_skill_items(
                items=all_skill_items,
                query=query,
                config=config,
            )
        elif resource == "memories":
            memory_tools = MemoryTools(context.store, config)
            all_memory_items = [
                _serialize_memory(skill)
                for skill in sorted(
                    await context.store.list_skills(),
                    key=lambda skill: str(getattr(skill, "title", "")).lower(),
                )
            ]
            ranked = (
                await memory_tools.minder_memory_recall(
                    query, limit=max(len(all_memory_items), 1)
                )
                if query
                else all_memory_items
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
