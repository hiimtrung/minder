"""MCP resource registration for Minder."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from minder.store.interfaces import IGraphRepository, IOperationalStore
from minder.domain.utils import _iso

_MINDER_INSTRUCTIONS = """\
# Minder MCP — Tool Usage Guide (26 tools)

Read this guide at session start. It tells you WHEN and in WHAT ORDER to call each tool.

## RULE 1 — No session, no work (mandatory pre-flight)

**Check first: do you have a `session_id` cached in this conversation?**

- **NO** → STOP. Call `minder_session_boot` immediately before any other tool:

  ```
  minder_session_boot(
      project_name="<project-slug>",
      project_context={"repo_path": "<absolute-path-to-repo>"}
  )
  ```

  Derive `project_name` from the repository folder name (e.g. `/home/dev/my-api` → `"my-api"`).
  `minder_session_boot` is idempotent — safe to call even if a session already exists.
  To restore a specific session by UUID: `minder_session_boot(project_name=..., session_id="<uuid>")`.

- **YES** → proceed with the cached `session_id`.

This rule applies without exception. Do not call search, workflow, memory, or skill tools before
establishing a session.

## RULE 2 — Deferred tool discovery

In some environments (e.g. Claude Code), Minder tool **schemas** are deferred — you see tool names
only. Calling a deferred tool without loading its schema first fails with `InputValidationError`.

**In Claude Code — load schemas FIRST, before any other action:**

```
ToolSearch(query="select:mcp__minder__minder_session_boot")
```

Call `minder_session_boot` immediately after. Always use `select:` with exact names — keyword
searches often miss the `mcp__minder__` prefix.

- Read `_next_steps` in **every** tool response — these inline hints tell you what to call next.
- NEVER fall back to generic file/bash tools because a Minder tool appears missing — load it first.

## Session state to cache throughout the session

After startup, keep these values in your working context:

| Value | Source | Used in |
|-------|--------|---------|
| `session_id` | `minder_session_boot` | every session_save, summarize call |
| `repo_id` | `minder://repos` resource or `session.project_context` | workflow_*, search_code, search_graph, find_impact |
| `repo_path` | `minder://repos` or `session.project_context.repo_path` | search_code, search_graph, find_impact |
| `current_step` | `minder_workflow_step` response | workflow_guard, skill_recall, workflow_update |

## Session startup — standard sequence

1. `minder_session_boot(project_name="<slug>", project_context={"repo_path": "<path>"})`:
   - Find-or-create a session in one call.
   - Returns `session_id`, `session_found`, prior `state`, `session_summary`, and `_next_steps`.
   - Cache `session_id`. If `session_found=true`, read `session_summary` — it has prior task and next actions.
   - Follow `_next_steps` in the response.

2. If boot response contains `repo_id` — **run in parallel**:
   - `minder_workflow_step(repo_id=<repo_id>, repo_path=<path>)` → cache `current_step`
   - `minder_skill_recall(query=<task>, current_step=<step>)` → load step conventions
   - Pass `include_definition=true` on the first call to also get the full workflow definition.

3. If boot response has **no** `repo_id`:
   - `minder_skill_recall(query=<task>)` + `minder_memory_recall(query=<task>)` — no repo required.
   - Read `minder://repos` only if you need to link the session to a registered repository.

## Per-step workflow sequence

Before starting or switching to a new workflow step:
1. `minder_workflow_guard(repo_id=<repo_id>, requested_step=<step-name>)` — **MANDATORY**. If `allowed=false`, stop. No exceptions.
2. `minder_skill_recall(query=<task>, current_step=<step-name>)` — load step conventions and checklists.
3. Do the work (search, implement, review, etc.).
4. `minder_workflow_update(repo_id=<repo_id>, completed_step=<step-name>, artifact_name=<artifact>, artifact_content=<content>)` — only when ALL required artifacts are complete.
5. `minder_session_save(session_id=<session_id>, state={"task": ..., "step": ..., "next_steps": [...]})` — checkpoint.

## Memory vs Skills — reading AND writing

Ask yourself one question:

> "Is this knowledge ONLY applicable to THIS specific project or client?"
> - **YES** → `minder_memory_*`  (project-specific fact, decision, constraint)
> - **NO**  → `minder_skill_*`   (reusable pattern, checklist, convention)

### Decision table

| Content | Correct pair |
|---------|-------------|
| "This project uses cursor-based pagination, not offset" | `memory_store` / `memory_recall` |
| "Auth token TTL is 15 min — non-configurable in this service" | `memory_store` / `memory_recall` |
| "We always deploy staging before prod in this repo" | `memory_store` / `memory_recall` |
| Cursor-based pagination pattern for REST APIs (reusable) | `skill_store` / `skill_recall` |
| JWT expiry handling checklist | `skill_store` / `skill_recall` |
| Blue-green deployment checklist | `skill_store` / `skill_recall` |

To **update** an existing memory: `minder_memory_store(memory_id=<id>, title=..., content=...)`.
To **update** an existing skill: `minder_skill_store(skill_id=<id>, ...)`. Pass `deprecated=True` to retire.

Skills are project-agnostic — `minder_skill_recall` does NOT require `repo_path`.
Do NOT call both recall tools with the same query — choose one based on the table above.

## Code search — which tool to use

| Query type | Tool |
|------------|------|
| "Where is X implemented / defined?" | `minder_search_code(query=..., repo_path=...)` |
| "Which routes / symbols call X?" | `minder_search_graph(query=..., repo_path=...)` |
| "What depends on file / module Y?" | `minder_find_impact(target=..., repo_path=...)` |
| "Has this error occurred before?" | `minder_search_errors(query=...)` — no repo_path needed |

Call `minder_find_impact` before modifying any shared module, route, or service.

## Tool dependency map — what you need before each call

| Tool | Requires |
|------|---------|
| `minder_workflow_*` | `session_id` + `repo_id` |
| `minder_search_code` / `minder_search_graph` / `minder_find_impact` | `session_id` + `repo_path` |
| `minder_skill_recall` / `minder_skill_store` | `session_id` (no repo needed) |
| `minder_memory_recall` / `minder_memory_store` | `session_id` (no repo needed) |
| `minder_session_save` / `minder_session_summarize` | `session_id` |
| `minder_workflow_guard` | `session_id` + `repo_id` + `current_step` from workflow_step |
| `minder_workflow_update` | all of the above + completed artifacts |

## Session context — branch and file tracking

When switching git branches or opening new files, pass them directly to `minder_session_save`:

```
minder_session_save(session_id=..., state={...}, branch="feature/my-branch", open_files=["src/foo.py"])
```

No separate context tool required.

## How to obtain repo_id and repo_path

- Read `minder://repos` resource — returns a list with `id` (UUID) and `path` for each registered repository.
- Or read `session.project_context` from `minder_session_boot` — may contain `repo_id` and `repo_path`.
- If the repo is not yet registered, skip workflow tools and store `repo_path` in `project_context` via `minder_session_save`.

## Session save frequency

Save after any of:
- A significant decision or constraint established
- Files changed or artifacts created
- Completing a workflow step
- Returning control to the user after multi-step work

Rule of thumb: every 5–10 user messages. Context is lost on `/compact` without a save.

## Wrapping up / before /compact

1. `minder_session_save(session_id=..., state={current progress snapshot})` — persist state.
2. `minder_session_summarize(session_id=...)` — structured summary (task, steps done, blockers, next actions). Recovered by `minder_session_boot` on next session.

Call `minder_session_summarize` proactively when the conversation exceeds ~20 exchanges.

## SubAgent delegation

1. `minder_agent_list(workflow_step=<current_step>)` — discover agents scoped to the current step.
2. `minder_agent_get(name=<agent-name>)` — load full system_prompt and tool list before spawning.
3. Spawn the agent using the loaded prompt and tools.

## Things to avoid

- Do NOT call any Minder tool before establishing a session (`minder_session_boot`). No exceptions.
- Do NOT fall back to generic bash/file tools when Minder tools appear missing — they are deferred, not absent.
- Do NOT call `minder_auth_whoami()` during startup — `minder_session_boot` already confirms auth. Only call it to inspect available scopes.
- Do NOT write project-specific facts to `minder_skill_store` — use `minder_memory_store`.
- Do NOT write reusable patterns to `minder_memory_store` — use `minder_skill_store`.
- Do NOT call `minder_memory_recall` AND `minder_skill_recall` with the same query — choose one.
- Do NOT call `minder_session_list` when you know the project name — use `minder_session_boot`.
- Do NOT skip `minder_workflow_guard` before starting any workflow step.
- Do NOT skip `minder_session_save` after significant work.

## Recovery — if you deviated from the startup sequence

If you never called `minder_session_boot`:
1. Call `minder_session_boot(project_name='<slug>', project_context={"repo_path": "<path>"})`.
2. Call `minder_workflow_step(repo_id=..., repo_path=...)` to sync workflow position.
3. Call `minder_skill_recall` and `minder_memory_recall` for the current task.
4. Call `minder_session_save(session_id=..., state={...})` to checkpoint.
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
