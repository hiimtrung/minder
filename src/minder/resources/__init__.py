"""MCP resource registration for Minder."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from minder.store.interfaces import IGraphRepository, IOperationalStore


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
            skills = await store.list_skills()
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
                result.append(
                    {
                        "id": str(repo.id),
                        "name": repo.repo_name,
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
    metadata = getattr(node, "node_metadata", {}) or {}
    return {
        "id": str(getattr(node, "id")),
        "node_type": str(getattr(node, "node_type", "")),
        "name": str(getattr(node, "name", "")),
        "metadata": metadata if isinstance(metadata, dict) else {},
    }


async def _repo_graph_nodes(graph_store: IGraphRepository, repo_name: str) -> list[Any]:
    nodes = await graph_store.list_nodes()
    selected: list[Any] = []
    for node in nodes:
        metadata = getattr(node, "node_metadata", {}) or {}
        project = str(metadata.get("project", "") or "")
        path_value = str(metadata.get("path", "") or "")
        if project == repo_name:
            selected.append(node)
            continue
        if path_value:
            try:
                if Path(path_value).name == repo_name:
                    selected.append(node)
            except (TypeError, ValueError):
                continue
    return selected
