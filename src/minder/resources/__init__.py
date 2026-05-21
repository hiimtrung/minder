"""MCP resource registration for Minder."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from minder.store.interfaces import IGraphRepository, IOperationalStore
from minder.utils import _iso

_MINDER_INSTRUCTIONS = """\
# Minder MCP — Tool Usage Guide

Read this guide at session start. It tells you WHEN and in WHAT ORDER to call each tool.

## Session state to preserve throughout the session

After startup, cache and reuse these values in every subsequent call:
- `session_id` (UUID string returned by `minder_session_find` or `minder_session_create`)
- `repo_id` (UUID string from the repository record — found in `minder://repos` resource or session project_context)
- `current_step` (string: the workflow step name, e.g. `"implement"`, `"review"`, `"write_tests"`)

## Session startup — core sequence (always do this)

1. `minder_session_find(name="<project-slug>")` — attempt to recover prior context.
   - Found → cache `session_id` and any `repo_id` / `current_step` from the response. Go to step 2.
   - Not found → call `minder_session_create(name="<project-slug>")`, cache the returned `session_id`.
2. If `repo_id` is known: `minder_workflow_step(repo_id=<repo_id>)` — get `current_step` and workflow position. If you need the full workflow definition (step list, transitions): call `minder_workflow_get(repo_id=<repo_id>, repo_path=<repo_path>)` once — cache the result for the rest of the session.

Do NOT call `minder_session_create` if `minder_session_find` returns a result.
Do NOT call `minder_workflow_get` more than once per session — it's expensive and the definition doesn't change.

## Session startup — optional enrichment (call when relevant)

After the core sequence, call these when the task warrants it:
- `minder_skill_recall(query=<task>, current_step=<current_step>)` — if you are about to start a workflow step and want to load conventions. Skills are project-agnostic; no `repo_path` needed.
- `minder_memory_recall(query=<task>)` — if the task may depend on prior project-specific decisions or constraints.

## Per-step workflow sequence

Before starting or switching to a new workflow step:
1. `minder_workflow_guard(repo_id=<repo_id>, requested_step=<step-name>)` — MANDATORY. Step name is a lowercase string (e.g. `"implement"`, `"review"`, `"write_tests"`). If guard returns `passed=false`, stop and surface the blocking reason.
2. `minder_skill_recall(query=<task>, current_step=<step-name>)` — load step conventions and checklists.
3. Do the work (search, implement, review, etc.).
4. `minder_workflow_update(repo_id=<repo_id>, completed_step=<step-name>, artifact_name=<artifact>, artifact_content=<content>)` — advance workflow only when ALL required artifacts are complete.
5. `minder_session_save(session_id=<session_id>, state={"task": ..., "step": ..., "next_steps": [...]})` — checkpoint.

## Memory vs Skills — how to choose

Choose ONE of the two recall tools per query. Use this decision rule:
- "How do **we** do X in this project?" (possessive, project-scoped) → `minder_memory_recall`
- "How to do X?" (general, cross-project) → `minder_skill_recall`

| Situation | Tool |
|-----------|------|
| Project-specific decision, constraint, or fact | `minder_memory_recall` |
| Reusable pattern, checklist, coding convention | `minder_skill_recall` |
| Prior architectural choice for THIS project | `minder_memory_recall` |
| Standard workflow step checklist | `minder_skill_recall` |

Skills are project-agnostic — `minder_skill_recall` does NOT require `repo_path`.
Do NOT call both tools with the same query.

## Code search — which tool to use

| Query type | Tool |
|------------|------|
| "Where is X implemented / defined?" | `minder_search_code(query=..., repo_path=...)` |
| "Which routes / symbols call X?" | `minder_search_graph(query=..., repo_path=...)` |
| "What depends on file / module Y?" | `minder_find_impact(target=..., repo_path=...)` |
| "Has this error occurred before?" | `minder_search_errors(query=...)` — no repo_path needed |

Call `minder_find_impact` before modifying any shared module, route, or service — not just when explicitly asked.

## How to obtain repo_id and repo_path

- Check the `minder://repos` resource for a list of registered repositories (includes `id` and `path`).
- Or check the session's `project_context` returned by `minder_session_find` (may contain `repo_id`, `repo_path`).
- The `repo_path` is an absolute filesystem path; `repo_id` is the UUID stored in Minder.

## Session save frequency

Save after any of:
- A significant decision or constraint established
- Files changed or artifacts created
- Completing a workflow step
- Returning control to the user after multi-step work

As a rule of thumb: save every 5–10 user messages. Do not wait until end of session — context is lost on /compact without a save.

## Wrapping up / before /compact

When ending a session or before any long gap:
1. `minder_session_save(session_id=..., state={current progress snapshot})` — save current state.
2. `minder_session_summarize(session_id=...)` — create a structured summary (task, steps done, blockers, next actions). This summary is returned by `minder_session_find` on the next session — use it to orient yourself immediately.

Call `minder_session_summarize` proactively when the conversation exceeds ~20 exchanges, even if the user has not mentioned /compact.

## SubAgent delegation

1. `minder_agent_list(workflow_step=<current_step>)` — filter by current step to find relevant agents.
2. `minder_agent_get(name=<agent-name>)` — load the full system_prompt and tool list before spawning.
3. Spawn the agent using the loaded prompt and tools.

## Things to avoid

- Do NOT call `minder_auth_ping` during normal work (connectivity test only).
- Do NOT call `minder_memory_compact` unless explicitly asked or `minder_memory_list` returns >10 overlapping entries.
- Do NOT call `minder_session_list` when you know the project name — use `minder_session_find`.
- Do NOT call `minder_workflow_get` more than once per session — call it during startup if you need the full workflow definition, then cache the result.
- Do NOT call `minder_session_create` if `minder_session_find` already found the session.
- Do NOT skip `minder_workflow_guard` before starting any workflow step — no exceptions.
- Do NOT call `minder_skill_import_git` during normal agent workflows — operator/admin use only.
- Do NOT call `minder_memory_recall` AND `minder_skill_recall` with the same query — choose based on the table above.
"""


class ResourceRegistry:
    """Registers all Minder MCP resources onto a :class:`FastMCP` app."""

    @staticmethod
    def register(
        app: FastMCP,
        store: IOperationalStore,
        graph_store: IGraphRepository | None = None,
    ) -> None:
        """Register core Minder resources, and graph resources when available.

        Args:
            app:   The FastMCP application to register resources with.
            store: An initialised operational store used to fetch live data.
        """

        # ------------------------------------------------------------------
        # minder://instructions
        # ------------------------------------------------------------------

        @app.resource(
            "minder://instructions",
            name="minder_instructions",
            title="Minder Tool Usage Guide",
            description=(
                "Complete guide for when and how to call Minder tools in the correct order. "
                "Load this resource at session start before calling any tools."
            ),
            mime_type="text/markdown",
        )
        async def instructions_resource() -> str:
            return _MINDER_INSTRUCTIONS

        # ------------------------------------------------------------------
        # minder://skills
        # ------------------------------------------------------------------

        @app.resource(
            "minder://skills",
            name="minder_skills",
            title="Minder Skills",
            description=(
                "List all stored skills with their id, title, language, and tags."
            ),
            mime_type="application/json",
        )
        async def skills_resource() -> str:
            skills = await store.list_skills_by_kind(is_memory=False)
            return json.dumps(
                [
                    {
                        "id": str(s.id),
                        "title": s.title,
                        "language": getattr(s, "language", ""),
                        "tags": list(s.tags) if s.tags else [],
                    }
                    for s in skills
                ],
                indent=2,
            )

        # ------------------------------------------------------------------
        # minder://repos
        # ------------------------------------------------------------------

        @app.resource(
            "minder://repos",
            name="minder_repos",
            title="Minder Repositories",
            description=(
                "List all repositories with their name, URL, and current workflow state."
            ),
            mime_type="application/json",
        )
        async def repos_resource() -> str:
            from pathlib import Path as _Path

            repos = await store.list_repositories()
            result: list[dict[str, Any]] = []
            for repo in repos:
                state = await store.get_workflow_state_by_repo(repo.id)
                workflow_info: dict[str, Any] | None = None
                if state is not None:
                    workflow_info = {
                        "current_step": state.current_step,
                        "completed_steps": list(state.completed_steps),
                        "blocked_by": list(state.blocked_by),
                    }
                # Derive repo_path from state_path (e.g. /repo/.minder → /repo)
                state_path = str(getattr(repo, "state_path", "") or "")
                if state_path:
                    sp = _Path(state_path)
                    repo_path = str(sp.parent) if sp.name == ".minder" else state_path
                else:
                    repo_path = None
                result.append(
                    {
                        "id": str(repo.id),
                        "name": repo.repo_name,
                        "path": repo_path,
                        "url": getattr(repo, "repo_url", ""),
                        "workflow_state": workflow_info,
                    }
                )
            return json.dumps(result, indent=2)

        # ------------------------------------------------------------------
        # minder://stats
        # ------------------------------------------------------------------

        @app.resource(
            "minder://stats",
            name="minder_stats",
            title="Minder Statistics",
            description=(
                "Aggregated counts: total skills, repos, workflows, and recorded errors."
            ),
            mime_type="application/json",
        )
        async def stats_resource() -> str:
            skills = await store.list_skills()
            repos = await store.list_repositories()
            workflows = await store.list_workflows()
            errors = await store.list_errors()
            return json.dumps(
                {
                    "skill_count": len(skills),
                    "repo_count": len(repos),
                    "workflow_count": len(workflows),
                    "error_count": len(errors),
                },
                indent=2,
            )

        if graph_store is None:
            return

        @app.resource(
            "minder://repos/{repo_name}/structure",
            name="minder_repo_structure",
            title="Minder Repository Structure",
            description="Graph-backed structural summary for a repository, grouped by node type.",
            mime_type="application/json",
        )
        async def repo_structure_resource(repo_name: str) -> str:
            repo_nodes = await _repo_graph_nodes(graph_store, repo_name)
            counts = Counter(str(getattr(node, "node_type", "")) for node in repo_nodes)
            grouped: dict[str, list[dict[str, Any]]] = {}
            for node in sorted(
                repo_nodes,
                key=lambda item: (
                    str(getattr(item, "node_type", "")),
                    str(getattr(item, "name", "")),
                ),
            ):
                item = _serialize_graph_node(node)
                grouped.setdefault(item["node_type"], []).append(item)
            return json.dumps(
                {
                    "repo_name": repo_name,
                    "counts": dict(counts),
                    "nodes": grouped,
                },
                indent=2,
            )

        @app.resource(
            "minder://repos/{repo_name}/todos",
            name="minder_repo_todos",
            title="Minder Repository TODOs",
            description="Graph-backed TODO items extracted for a repository.",
            mime_type="application/json",
        )
        async def repo_todos_resource(repo_name: str) -> str:
            repo_nodes = await _repo_graph_nodes(graph_store, repo_name)
            todos = [
                _serialize_graph_node(node)
                for node in repo_nodes
                if str(getattr(node, "node_type", "")) == "todo"
            ]
            todos.sort(
                key=lambda item: (
                    str(item["metadata"].get("path", "")),
                    int(item["metadata"].get("line", 0) or 0),
                    item["name"],
                )
            )
            return json.dumps(
                {
                    "repo_name": repo_name,
                    "count": len(todos),
                    "items": todos,
                },
                indent=2,
            )

        @app.resource(
            "minder://repos/{repo_name}/routes",
            name="minder_repo_routes",
            title="Minder Repository Routes",
            description="Graph-backed route inventory for a repository.",
            mime_type="application/json",
        )
        async def repo_routes_resource(repo_name: str) -> str:
            repo_nodes = await _repo_graph_nodes(graph_store, repo_name)
            routes = [
                _serialize_graph_node(node)
                for node in repo_nodes
                if str(getattr(node, "node_type", "")) == "route"
            ]
            routes.sort(
                key=lambda item: (
                    str(item["metadata"].get("method", "")),
                    str(item["metadata"].get("route_path", "")),
                    item["name"],
                )
            )
            return json.dumps(
                {
                    "repo_name": repo_name,
                    "count": len(routes),
                    "items": routes,
                },
                indent=2,
            )

        @app.resource(
            "minder://repos/{repo_name}/dependencies",
            name="minder_repo_dependencies",
            title="Minder Repository Dependencies",
            description="Graph-backed internal and external dependency summary for a repository.",
            mime_type="application/json",
        )
        async def repo_dependencies_resource(repo_name: str) -> str:
            repo_nodes = await _repo_graph_nodes(graph_store, repo_name)
            repo_node_ids = {str(getattr(node, "id")) for node in repo_nodes}
            services = [node for node in repo_nodes if str(getattr(node, "node_type", "")) == "service"]
            internal_dependencies: list[dict[str, Any]] = []
            for service in services:
                neighbors = await graph_store.get_neighbors(getattr(service, "id"), direction="out", relation="depends_on")
                targets = [
                    {
                        "id": str(getattr(neighbor, "id")),
                        "name": str(getattr(neighbor, "name", "")),
                        "node_type": str(getattr(neighbor, "node_type", "")),
                    }
                    for neighbor in neighbors
                    if str(getattr(neighbor, "id")) in repo_node_ids
                ]
                if targets:
                    internal_dependencies.append(
                        {
                            "service": str(getattr(service, "name", "")),
                            "depends_on": sorted(targets, key=lambda item: item["name"]),
                        }
                    )

            external_apis = [
                _serialize_graph_node(node)
                for node in repo_nodes
                if str(getattr(node, "node_type", "")) == "external_service_api"
            ]
            external_apis.sort(key=lambda item: item["name"])
            return json.dumps(
                {
                    "repo_name": repo_name,
                    "internal_dependencies": internal_dependencies,
                    "external_services": external_apis,
                },
                indent=2,
            )

        @app.resource(
            "minder://repos/{repo_name}/symbols",
            name="minder_repo_symbols",
            title="Minder Repository Symbols",
            description="Graph-backed symbol inventory for functions, classes, controllers, and interfaces within a repository.",
            mime_type="application/json",
        )
        async def repo_symbols_resource(repo_name: str) -> str:
            repo_nodes = await _repo_graph_nodes(graph_store, repo_name)
            symbol_types = {"function", "class", "controller", "interface", "abstract_class", "module"}
            symbols = [
                _serialize_graph_node(node)
                for node in repo_nodes
                if str(getattr(node, "node_type", "")) in symbol_types
            ]
            symbols.sort(
                key=lambda item: (
                    item["node_type"],
                    str(item["metadata"].get("path", "")),
                    item["name"],
                )
            )
            return json.dumps(
                {
                    "repo_name": repo_name,
                    "count": len(symbols),
                    "items": symbols,
                },
                indent=2,
            )


def _serialize_graph_node(node: Any) -> dict[str, Any]:
    """Helper to convert GraphNode to dict for JSON serialization."""
    return {
        "id": str(node.id),
        "node_type": node.node_type,
        "name": node.name,
        "metadata": node.extra_metadata or {},
        "created_at": _iso(node.created_at),
    }


async def _repo_graph_nodes(graph_store: IGraphRepository, repo_name: str) -> list[Any]:
    """Helper to get and filter nodes for a specific repository."""
    all_nodes = await graph_store.list_nodes()
    selected = []
    for node in all_nodes:
        metadata = node.extra_metadata or {}
        project = str(metadata.get("project", "") or "")
        if project == repo_name:
            selected.append(node)
            continue
        
        # Fallback for older nodes or special cases
        path_value = str(metadata.get("path", "") or "")
        if path_value:
            try:
                if Path(path_value).name == repo_name:
                    selected.append(node)
            except (TypeError, ValueError):
                continue
    return selected
