from __future__ import annotations

import math
from typing import Any, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from minder.config import MinderConfig
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


# Lexical scoring removed in favor of semantic-only search as requested.


async def _rank_serialized_items(
    *,
    items: list[Any],
    query: str,
    text_builder: Callable[[Any], str],
    context: AdminRouteContext,
) -> list[Any]:
    if not query.strip() or not items:
        return items

    # For mxbai and similar models, queries often perform better with a prefix.
    query_text = f"Represent this sentence for searching relevant passages: {query}"
    query_embedding = context.embedder.embed(query_text)
    candidates: list[tuple[Any, str]] = []
    for item in items:
        text = text_builder(item).strip()
        if text:
            candidates.append((item, text))

    if not candidates:
        return items

    candidate_texts = [c[1] for c in candidates]
    candidate_embeddings = context.embedder.embed_many(candidate_texts)

    ranked: list[Any] = []
    for (item, _), candidate_embedding in zip(
        candidates, candidate_embeddings, strict=False
    ):
        score = _cosine_similarity(query_embedding, candidate_embedding)
        ranked.append({**item, "search_score": round(score, 4)})

    ranked.sort(
        key=lambda item: (
            -float(item.get("search_score", 0.0) or 0.0),
            str(item.get("title") or item.get("name") or item.get("id") or "").lower(),
        )
    )
    return ranked


async def _rank_skill_items(
    *,
    items: list[dict[str, Any]],
    query: str,
    context: AdminRouteContext,
) -> list[dict[str, Any]]:
    if not query.strip() or not items:
        return items

    # For mxbai and similar models, queries often perform better with a prefix.
    query_text = f"Represent this sentence for searching relevant passages: {query}"
    query_embedding = context.embedder.embed(query_text)
    candidates: list[tuple[dict[str, Any], str]] = []
    for item in items:
        title = str(item.get("title", "") or "")
        language = str(item.get("language", "") or "")
        tags = [str(tag) for tag in list(item.get("tags", []) or [])]

        # Build a more balanced candidate text for skills
        # We give weight to title and tags, and truncate content to avoid diluting semantic focus
        content_snippet = str(item.get("content", "") or "")[:2000]
        candidate_text = f"Title: {title}\nLanguage: {language}\nTags: {', '.join(tags)}\nContent: {content_snippet}".strip()

        if candidate_text:
            candidates.append((item, candidate_text))

    if not candidates:
        return items

    candidate_texts = [c[1] for c in candidates]
    candidate_embeddings = context.embedder.embed_many(candidate_texts)

    ranked: list[dict[str, Any]] = []
    for (item, _), candidate_embedding in zip(
        candidates, candidate_embeddings, strict=False
    ):
        semantic_score = _cosine_similarity(query_embedding, candidate_embedding)
        # We keep a tiny quality boost but rely on semantic similarity for the core ranking.
        score = semantic_score + (
            min(float(item.get("quality_score", 0.0) or 0.0), 1.0) * 0.01
        )
        ranked.append(
            {
                **item,
                "search_score": round(score, 4),
                "semantic_score": round(semantic_score, 4),
                "lexical_score": 0.0,
            }
        )

    ranked.sort(
        key=lambda item: (
            -float(item.get("search_score", 0.0) or 0.0),
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
            limit = max(1, min(int(request.query_params.get("limit", "20")), 100))
            offset = max(0, int(request.query_params.get("offset", "0")))
        except ValueError:
            return JSONResponse({"error": "Invalid limit or offset"}, status_code=400)

        await record_admin_operation(
            operation=f"search_{resource or 'catalog'}",
            outcome="success",
            actor_id="system",
            store=context.store,
        )

        ranked: list[Any] = []

        if resource == "clients":
            client_items = (await context.use_cases.list_clients())["clients"]
            ranked = await _rank_serialized_items(
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
                context=context,
            )
        elif resource == "repositories":
            repo_items = (await context.use_cases.list_repositories())["repositories"]
            ranked = await _rank_serialized_items(
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
                context=context,
            )
        elif resource == "workflows":
            workflow_items = (await context.use_cases.list_workflows())["workflows"]
            ranked = await _rank_serialized_items(
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
                context=context,
            )
        elif resource == "prompts":
            prompt_items = await _prompt_items(context)
            ranked = await _rank_serialized_items(
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
                context=context,
            )
        elif resource == "skills":
            skill_tools = SkillTools(context.store, context.config)
            all_skill_items = await skill_tools.minder_skill_list()
            all_skill_items = [
                s
                for s in all_skill_items
                if s.get("language") not in ("markdown", "text", "")
                or s.get("source") is not None
            ]
            ranked = await _rank_skill_items(
                items=all_skill_items,
                query=query,
                context=context,
            )
        elif resource == "memories":
            all_skills = await context.store.list_skills()
            all_memory_items = [
                _serialize_memory(skill)
                for skill in all_skills
                if getattr(skill, "language", "") in ("markdown", "text", "", None)
                and getattr(skill, "source_metadata", None) is None
            ]
            if query:
                memory_tools = MemoryTools(context.store, context.config)
                ranked = await memory_tools.minder_memory_recall(
                    query, limit=max(len(all_memory_items), 1)
                )
                ranked = [
                    item
                    for item in ranked
                    if item.get("language") in ("markdown", "text", "", None)
                    and item.get("source") is None
                ]
            else:
                ranked = sorted(
                    all_memory_items,
                    key=lambda m: str(m.get("title", "")).lower(),
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
