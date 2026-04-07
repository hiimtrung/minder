"""
MCP Resource registration for Minder.

Provides three read-only resources that MCP clients can subscribe to:

``minder://skills``
    JSON array of all stored skills — id, title, language, tags.

``minder://repos``
    JSON array of repositories with their current workflow state.

``minder://stats``
    JSON object with aggregate counts: skills, repos, workflows, errors.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from minder.store.interfaces import IOperationalStore


class ResourceRegistry:
    """Registers all Minder MCP resources onto a :class:`FastMCP` app."""

    @staticmethod
    def register(app: FastMCP, store: IOperationalStore) -> None:
        """Register ``minder://skills``, ``minder://repos``, and ``minder://stats``.

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
