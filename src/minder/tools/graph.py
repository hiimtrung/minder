from __future__ import annotations

from typing import Any

from minder.store.interfaces import IGraphRepository, IRepositoryRepo
from minder.application.graph.service import GraphService


class GraphTools:
    def __init__(
        self,
        graph_store: IGraphRepository | None,
        repository_store: IRepositoryRepo | None = None,
    ) -> None:
        self._service = GraphService(
            graph_store=graph_store,
            repository_store=repository_store,
        )

    async def list_repo_nodes(
        self,
        *,
        repo_id: str | None = None,
        repo_name: str | None = None,
        repo_path: str | None = None,
        branch: str | None = None,
        node_types: list[str] | None = None,
    ) -> tuple[str, list[Any]]:
        return await self._service.list_repo_nodes(
            repo_id=repo_id,
            repo_name=repo_name,
            repo_path=repo_path,
            branch=branch,
            node_types=node_types,
        )

    async def list_repo_graph(
        self,
        *,
        repo_id: str | None = None,
        repo_name: str | None = None,
        repo_path: str | None = None,
        branch: str | None = None,
        node_types: list[str] | None = None,
    ) -> tuple[str, list[Any], list[Any]]:
        return await self._service.list_repo_graph(
            repo_id=repo_id,
            repo_name=repo_name,
            repo_path=repo_path,
            branch=branch,
            node_types=node_types,
        )

    async def minder_search_graph(
        self,
        query: str,
        *,
        repo_path: str | None = None,
        repo_id: str | None = None,
        repo_name: str | None = None,
        branch: str | None = None,
        node_types: list[str] | None = None,
        languages: list[str] | None = None,
        last_states: list[str] | None = None,
        limit: int = 10,
        include_linked_repos: bool = False,
        landscape_hops: int = 1,
        allowed_repo_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._service.minder_search_graph(
            query=query,
            repo_path=repo_path,
            repo_id=repo_id,
            repo_name=repo_name,
            branch=branch,
            node_types=node_types,
            languages=languages,
            last_states=last_states,
            limit=limit,
            include_linked_repos=include_linked_repos,
            landscape_hops=landscape_hops,
            allowed_repo_scopes=allowed_repo_scopes,
        )

    async def minder_find_impact(
        self,
        target: str,
        *,
        repo_path: str | None = None,
        repo_id: str | None = None,
        repo_name: str | None = None,
        branch: str | None = None,
        depth: int = 2,
        limit: int = 25,
        include_linked_repos: bool = False,
        landscape_hops: int = 1,
        allowed_repo_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._service.minder_find_impact(
            target=target,
            repo_path=repo_path,
            repo_id=repo_id,
            repo_name=repo_name,
            branch=branch,
            depth=depth,
            limit=limit,
            include_linked_repos=include_linked_repos,
            landscape_hops=landscape_hops,
            allowed_repo_scopes=allowed_repo_scopes,
        )

    async def build_cross_repo_context(
        self,
        query: str,
        *,
        repo_path: str | None = None,
        repo_id: str | None = None,
        repo_name: str | None = None,
        branch: str | None = None,
        allowed_repo_scopes: list[str] | None = None,
        limit: int = 5,
    ) -> tuple[str, dict[str, Any] | None]:
        return await self._service.build_cross_repo_context(
            query=query,
            repo_path=repo_path,
            repo_id=repo_id,
            repo_name=repo_name,
            branch=branch,
            allowed_repo_scopes=allowed_repo_scopes,
            limit=limit,
        )
