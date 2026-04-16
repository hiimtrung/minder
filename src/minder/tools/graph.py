from __future__ import annotations

from collections import Counter, deque
from pathlib import Path
from typing import Any

from minder.store.interfaces import IGraphRepository
from minder.store.interfaces import IRepositoryRepo


class GraphTools:
    def __init__(
        self,
        graph_store: IGraphRepository | None,
        repository_store: IRepositoryRepo | None = None,
    ) -> None:
        self._graph_store = graph_store
        self._repository_store = repository_store

    async def list_repo_nodes(
        self,
        *,
        repo_id: str | None = None,
        repo_name: str | None = None,
        repo_path: str | None = None,
        branch: str | None = None,
    ) -> tuple[str, list[Any]]:
        if self._graph_store is None:
            raise RuntimeError("Graph store is not configured")

        effective_repo_name, repo_root = _resolve_repo_identity(
            repo_name=repo_name,
            repo_path=repo_path,
        )

        # Fast path: if repo_id is known use the scoped query
        if repo_id and hasattr(self._graph_store, "list_nodes_by_scope"):
            repo_nodes = await self._graph_store.list_nodes_by_scope(
                repo_id=repo_id, branch=branch
            )
            return effective_repo_name, repo_nodes

        # Fallback: load all nodes and filter in Python (legacy / no-scope stores)
        all_nodes = await self._graph_store.list_nodes()
        repo_nodes = [
            node
            for node in all_nodes
            if _node_belongs_to_repo(
                node,
                repo_id=repo_id,
                repo_name=effective_repo_name,
                repo_root=repo_root,
                branch=branch,
            )
        ]
        return effective_repo_name, repo_nodes

    async def list_repo_graph(
        self,
        *,
        repo_id: str | None = None,
        repo_name: str | None = None,
        repo_path: str | None = None,
        branch: str | None = None,
    ) -> tuple[str, list[Any], list[Any]]:
        if self._graph_store is None:
            raise RuntimeError("Graph store is not configured")

        effective_repo_name, repo_nodes = await self.list_repo_nodes(
            repo_id=repo_id,
            repo_name=repo_name,
            repo_path=repo_path,
            branch=branch,
        )
        repo_node_ids = {getattr(node, "id") for node in repo_nodes}

        # Fast path: repo-scoped edge query
        if repo_id and hasattr(self._graph_store, "list_edges_by_scope"):
            all_edges = await self._graph_store.list_edges_by_scope(repo_id=repo_id)
        else:
            all_edges = await self._graph_store.list_edges()

        repo_edges = [
            edge
            for edge in all_edges
            if getattr(edge, "source_id", None) in repo_node_ids
            and getattr(edge, "target_id", None) in repo_node_ids
        ]
        return effective_repo_name, repo_nodes, repo_edges

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
        if self._graph_store is None:
            raise RuntimeError("Graph store is not configured")

        scopes = await self._graph_scopes(
            repo_id=repo_id,
            repo_name=repo_name,
            repo_path=repo_path,
            branch=branch,
            include_linked_repos=include_linked_repos,
            landscape_hops=landscape_hops,
            allowed_repo_scopes=allowed_repo_scopes,
        )
        effective_repo_name = (
            scopes[0]["repo_name"] if scopes else (repo_name or "unknown")
        )
        allowed_types = {
            node_type.strip() for node_type in (node_types or []) if node_type.strip()
        }
        allowed_languages = {
            language.strip().lower()
            for language in (languages or [])
            if language.strip()
        }
        allowed_states = {
            state.strip().lower() for state in (last_states or []) if state.strip()
        }

        matches: list[dict[str, Any]] = []
        for scope in scopes:
            _, repo_nodes = await self.list_repo_nodes(
                repo_id=scope["repo_id"],
                repo_name=scope["repo_name"],
                repo_path=scope["repo_path"],
                branch=scope["branch"],
            )
            for node in repo_nodes:
                node_type = str(getattr(node, "node_type", ""))
                if allowed_types and node_type not in allowed_types:
                    continue
                metadata = _metadata(node)
                language = str(metadata.get("language", "") or "").lower()
                last_state = str(metadata.get("last_state", "") or "").lower()
                if allowed_languages and language not in allowed_languages:
                    continue
                if allowed_states and last_state not in allowed_states:
                    continue
                score = _match_score(node, query)
                if score <= 0:
                    continue
                item = _serialize_node(node)
                item["score"] = score
                item["repo_id"] = scope["repo_id"]
                item["repo_name"] = scope["repo_name"]
                item["branch"] = scope["branch"]
                item["landscape_distance"] = scope["distance"]
                item["via_link"] = scope.get("via_link")
                matches.append(item)

        matches.sort(
            key=lambda item: (
                int(item.get("landscape_distance", 0)),
                -int(item["score"]),
                item["node_type"],
                item["name"],
            )
        )
        limited = matches[: max(1, limit)]
        return {
            "query": query,
            "repo_name": effective_repo_name,
            "searched_scopes": [self._serialize_scope(scope) for scope in scopes],
            "filters": {
                "node_types": sorted(allowed_types),
                "languages": sorted(allowed_languages),
                "last_states": sorted(allowed_states),
            },
            "scope_count": len(scopes),
            "count": len(limited),
            "results": limited,
        }

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
        if self._graph_store is None:
            raise RuntimeError("Graph store is not configured")

        scopes = await self._graph_scopes(
            repo_id=repo_id,
            repo_name=repo_name,
            repo_path=repo_path,
            branch=branch,
            include_linked_repos=include_linked_repos,
            landscape_hops=landscape_hops,
            allowed_repo_scopes=allowed_repo_scopes,
        )
        effective_repo_name = (
            scopes[0]["repo_name"] if scopes else (repo_name or "unknown")
        )
        all_matches: list[dict[str, Any]] = []
        impacted: list[dict[str, Any]] = []
        type_counter: Counter[str] = Counter()
        upstream_count = 0
        downstream_count = 0
        synthetic_landscape_count = 0

        for scope in scopes:
            _, repo_nodes = await self.list_repo_nodes(
                repo_id=scope["repo_id"],
                repo_name=scope["repo_name"],
                repo_path=scope["repo_path"],
                branch=scope["branch"],
            )
            matches = _resolve_matches(repo_nodes, target)
            if matches:
                for node in matches[: min(5, max(1, limit))]:
                    serialized = _serialize_node(node)
                    serialized["repo_id"] = scope["repo_id"]
                    serialized["repo_name"] = scope["repo_name"]
                    serialized["branch"] = scope["branch"]
                    serialized["landscape_distance"] = scope["distance"]
                    serialized["via_link"] = scope.get("via_link")
                    all_matches.append(serialized)

                repo_node_ids = {getattr(node, "id") for node in repo_nodes}
                visited = {getattr(node, "id") for node in matches}
                queue: deque[tuple[Any, int]] = deque(
                    (getattr(node, "id"), 0)
                    for node in matches[: min(5, max(1, limit))]
                )

                while queue and len(impacted) < limit:
                    node_id, current_depth = queue.popleft()
                    if current_depth >= max(1, depth):
                        continue

                    for direction in ("out", "in"):
                        neighbors = await self._graph_store.get_neighbors(
                            node_id, direction=direction
                        )
                        for neighbor in neighbors:
                            neighbor_id = getattr(neighbor, "id")
                            if (
                                neighbor_id not in repo_node_ids
                                or neighbor_id in visited
                            ):
                                continue
                            visited.add(neighbor_id)
                            queue.append((neighbor_id, current_depth + 1))
                            serialized = _serialize_node(neighbor)
                            serialized["direction"] = (
                                "downstream" if direction == "out" else "upstream"
                            )
                            serialized["distance"] = current_depth + 1
                            serialized["repo_id"] = scope["repo_id"]
                            serialized["repo_name"] = scope["repo_name"]
                            serialized["branch"] = scope["branch"]
                            serialized["landscape_distance"] = scope["distance"]
                            serialized["via_link"] = scope.get("via_link")
                            impacted.append(serialized)
                            type_counter.update([serialized["node_type"]])
                            if direction == "out":
                                downstream_count += 1
                            else:
                                upstream_count += 1
                            if len(impacted) >= limit:
                                break
                        if len(impacted) >= limit:
                            break
            elif scope["distance"] > 0 and len(impacted) < limit:
                impacted.append(
                    {
                        "id": f"landscape:{scope['repo_id']}:{scope['branch']}",
                        "node_type": "repository_branch",
                        "name": f"{scope['repo_name']}:{scope['branch']}",
                        "metadata": {
                            "repo_name": scope["repo_name"],
                            "branch": scope["branch"],
                            "landscape_only": True,
                        },
                        "direction": "cross_repo",
                        "distance": 1,
                        "repo_id": scope["repo_id"],
                        "repo_name": scope["repo_name"],
                        "branch": scope["branch"],
                        "landscape_distance": scope["distance"],
                        "via_link": scope.get("via_link"),
                    }
                )
                type_counter.update(["repository_branch"])
                synthetic_landscape_count += 1

        all_matches.sort(
            key=lambda item: (
                int(item.get("landscape_distance", 0)),
                item["node_type"],
                item["name"],
            )
        )
        seed_nodes = all_matches[: min(5, max(1, limit))]

        if not seed_nodes:
            return {
                "target": target,
                "repo_name": effective_repo_name,
                "searched_scopes": [self._serialize_scope(scope) for scope in scopes],
                "matches": [],
                "impacted": [],
                "summary": {
                    "match_count": 0,
                    "impacted_count": 0,
                    "upstream_count": 0,
                    "downstream_count": 0,
                    "scope_count": len(scopes),
                    "synthetic_landscape_count": 0,
                    "by_node_type": {},
                },
            }

        return {
            "target": target,
            "repo_name": effective_repo_name,
            "searched_scopes": [self._serialize_scope(scope) for scope in scopes],
            "matches": seed_nodes,
            "impacted": impacted[:limit],
            "summary": {
                "match_count": len(seed_nodes),
                "impacted_count": len(impacted[:limit]),
                "upstream_count": upstream_count,
                "downstream_count": downstream_count,
                "scope_count": len(scopes),
                "synthetic_landscape_count": synthetic_landscape_count,
                "by_node_type": dict(type_counter),
            },
        }

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
        if self._graph_store is None:
            return "", None

        result = await self.minder_search_graph(
            query,
            repo_path=repo_path,
            repo_id=repo_id,
            repo_name=repo_name,
            branch=branch,
            limit=limit,
            include_linked_repos=True,
            landscape_hops=1,
            allowed_repo_scopes=allowed_repo_scopes,
        )
        scopes = list(result.get("searched_scopes", []))
        if len(scopes) <= 1:
            return "", None

        link_descriptions: list[str] = []
        for scope in scopes[1:]:
            via_link = scope.get("via_link") or {}
            relation = str(via_link.get("relation", "depends_on") or "depends_on")
            link_descriptions.append(
                f"{scope['repo_name']}:{scope['branch']} via {relation}"
            )

        lines = [
            "Cross-repo landscape context is available for this repository.",
            f"Linked scopes: {', '.join(link_descriptions)}.",
        ]
        if result.get("results"):
            hits = [
                f"{item['repo_name']}:{item['branch']} -> {item['name']}"
                for item in result["results"][:limit]
            ]
            lines.append(
                "Related graph matches across linked scopes: " + "; ".join(hits) + "."
            )
        return "\n".join(lines), result

    async def _graph_scopes(
        self,
        *,
        repo_id: str | None,
        repo_name: str | None,
        repo_path: str | None,
        branch: str | None,
        include_linked_repos: bool,
        landscape_hops: int,
        allowed_repo_scopes: list[str] | None,
    ) -> list[dict[str, Any]]:
        root_repo = await self._resolve_repository(
            repo_id=repo_id,
            repo_name=repo_name,
            repo_path=repo_path,
        )
        effective_repo_name, _ = _resolve_repo_identity(
            repo_name=repo_name,
            repo_path=repo_path,
        )
        root_branch = (
            str(
                branch
                or (
                    getattr(root_repo, "default_branch", None)
                    if root_repo is not None
                    else None
                )
                or ""
            ).strip()
            or None
        )

        root_scope = {
            "repo_id": str(getattr(root_repo, "id", "") or repo_id or ""),
            "repo_name": str(
                getattr(root_repo, "repo_name", "") or effective_repo_name
            ),
            "repo_path": (
                self._repository_root_path(root_repo)
                if root_repo is not None
                else repo_path
            ),
            "branch": root_branch,
            "distance": 0,
            "via_link": None,
        }
        scopes = [root_scope]
        if not include_linked_repos or root_repo is None:
            return scopes
        linked = await self._expand_linked_scopes(
            root_repo=root_repo,
            branch=root_branch,
            max_hops=max(1, landscape_hops),
            allowed_repo_scopes=allowed_repo_scopes,
        )
        scopes.extend(linked)
        return scopes

    async def _expand_linked_scopes(
        self,
        *,
        root_repo: Any,
        branch: str | None,
        max_hops: int,
        allowed_repo_scopes: list[str] | None,
    ) -> list[dict[str, Any]]:
        repositories = await self._list_repositories()
        if not repositories:
            return []
        root_branch = str(
            branch or getattr(root_repo, "default_branch", None) or ""
        ).strip()
        start_key = (str(getattr(root_repo, "id")), root_branch)
        queue: deque[tuple[Any, str, int]] = deque([(root_repo, root_branch, 0)])
        visited = {start_key}
        scopes: list[dict[str, Any]] = []

        while queue:
            current_repo, current_branch, current_distance = queue.popleft()
            if current_distance >= max_hops:
                continue
            current_repo_id = str(getattr(current_repo, "id"))
            current_repo_name = str(getattr(current_repo, "repo_name", "") or "")

            for owner in repositories:
                owner_id = str(getattr(owner, "id"))
                for link in self._repository_branch_links(owner):
                    source_repo_id = str(link.get("source_repo_id", "") or owner_id)
                    source_branch = str(link.get("source_branch", "") or "").strip()
                    target_repo_id = str(link.get("target_repo_id", "") or "").strip()
                    target_repo_name = str(
                        link.get("target_repo_name", "") or ""
                    ).strip()
                    target_branch = str(link.get("target_branch", "") or "").strip()
                    if not source_branch or not target_branch:
                        continue

                    next_repo = None
                    next_branch = ""
                    via_link: dict[str, Any] | None = None
                    if (
                        source_repo_id == current_repo_id
                        and source_branch == current_branch
                    ):
                        next_repo = self._resolve_repository_reference(
                            repositories=repositories,
                            target_repo_id=target_repo_id,
                            target_repo_name=target_repo_name,
                            target_repo_url=link.get("target_repo_url"),
                        )
                        next_branch = target_branch
                        via_link = {
                            "relation": str(
                                link.get("relation", "depends_on") or "depends_on"
                            ),
                            "direction": "outbound",
                            "source_repo_name": current_repo_name,
                            "source_branch": current_branch,
                        }
                    elif (
                        target_repo_id == current_repo_id
                        and target_branch == current_branch
                    ):
                        next_repo = owner
                        next_branch = source_branch
                        via_link = {
                            "relation": str(
                                link.get("relation", "depends_on") or "depends_on"
                            ),
                            "direction": "inbound",
                            "source_repo_name": str(
                                getattr(owner, "repo_name", "") or ""
                            ),
                            "source_branch": source_branch,
                        }
                    if next_repo is None or not next_branch:
                        continue

                    next_key = (str(getattr(next_repo, "id")), next_branch)
                    if next_key in visited:
                        continue
                    if not _repo_matches_scopes(
                        next_repo,
                        self._repository_root_path(next_repo),
                        allowed_repo_scopes,
                    ):
                        continue
                    visited.add(next_key)
                    queue.append((next_repo, next_branch, current_distance + 1))
                    scopes.append(
                        {
                            "repo_id": str(getattr(next_repo, "id")),
                            "repo_name": str(getattr(next_repo, "repo_name", "") or ""),
                            "repo_path": self._repository_root_path(next_repo),
                            "branch": next_branch,
                            "distance": current_distance + 1,
                            "via_link": via_link,
                        }
                    )

        return scopes

    async def _resolve_repository(
        self,
        *,
        repo_id: str | None,
        repo_name: str | None,
        repo_path: str | None,
    ) -> Any | None:
        repositories = await self._list_repositories()
        if not repositories:
            return None
        normalized_repo_id = str(repo_id or "").strip()
        normalized_repo_name = str(repo_name or "").strip()
        normalized_repo_path = str(Path(repo_path).resolve()) if repo_path else ""
        for repository in repositories:
            if (
                normalized_repo_id
                and str(getattr(repository, "id")) == normalized_repo_id
            ):
                return repository
            if (
                normalized_repo_name
                and str(getattr(repository, "repo_name", "") or "")
                == normalized_repo_name
            ):
                return repository
            repository_root = self._repository_root_path(repository)
            if (
                normalized_repo_path
                and repository_root
                and str(Path(repository_root).resolve()) == normalized_repo_path
            ):
                return repository
        return None

    async def _list_repositories(self) -> list[Any]:
        if self._repository_store is None:
            return []
        return await self._repository_store.list_repositories()

    @staticmethod
    def _repository_root_path(repository: Any) -> str | None:
        if repository is None:
            return None
        state_path = str(getattr(repository, "state_path", "") or "")
        if not state_path:
            return None
        state_root = Path(state_path)
        if state_root.name == ".minder":
            return str(state_root.parent)
        return str(state_root)

    @staticmethod
    def _repository_branch_links(repository: Any) -> list[dict[str, Any]]:
        relationships = dict(getattr(repository, "relationships", {}) or {})
        raw_links = relationships.get("cross_repo_branches", [])
        if not isinstance(raw_links, list):
            return []
        return [dict(link) for link in raw_links if isinstance(link, dict)]

    @staticmethod
    def _resolve_repository_reference(
        *,
        repositories: list[Any],
        target_repo_id: Any,
        target_repo_name: Any,
        target_repo_url: Any,
    ) -> Any | None:
        normalized_target_id = str(target_repo_id or "").strip()
        normalized_target_name = str(target_repo_name or "").strip()
        normalized_target_url = _normalize_repository_remote(target_repo_url)
        for repository in repositories:
            if (
                normalized_target_id
                and str(getattr(repository, "id")) == normalized_target_id
            ):
                return repository
            if (
                normalized_target_url
                and _normalize_repository_remote(getattr(repository, "repo_url", None))
                == normalized_target_url
            ):
                return repository
            if (
                normalized_target_name
                and str(getattr(repository, "repo_name", "") or "")
                == normalized_target_name
            ):
                return repository
        return None

    @staticmethod
    def _serialize_scope(scope: dict[str, Any]) -> dict[str, Any]:
        return {
            "repo_id": scope["repo_id"],
            "repo_name": scope["repo_name"],
            "repo_path": scope["repo_path"],
            "branch": scope["branch"],
            "distance": scope["distance"],
            "via_link": scope.get("via_link"),
        }


def _metadata(node: Any) -> dict[str, Any]:
    value = getattr(node, "node_metadata", {}) or {}
    return value if isinstance(value, dict) else {}


def _resolve_repo_identity(
    *,
    repo_name: str | None,
    repo_path: str | None,
) -> tuple[str, Path | None]:
    if repo_path:
        repo_root = Path(repo_path).resolve()
        return repo_name or repo_root.name, repo_root
    return repo_name or "unknown", None


def _node_belongs_to_repo(
    node: Any,
    *,
    repo_id: str | None,
    repo_name: str,
    repo_root: Path | None,
    branch: str | None = None,
) -> bool:
    metadata = _metadata(node)

    # v2: check the actual repo_id column first
    node_repo_id = str(getattr(node, "repo_id", "") or "")
    if repo_id and node_repo_id:
        if node_repo_id != repo_id:
            return False
        # Branch filter
        if branch is not None:
            node_branch = str(getattr(node, "branch", "") or "")
            if node_branch and node_branch != branch:
                return False
        return True

    # Legacy fallback: repo_id stored inside metadata JSON
    meta_repo_id = str(metadata.get("repo_id", "") or "")
    if repo_id and meta_repo_id:
        if meta_repo_id != repo_id:
            return False
        if branch is not None:
            meta_branch = str(metadata.get("branch", "") or "")
            if meta_branch and meta_branch != branch:
                return False
        return True

    # Further legacy: match by project/repo name
    project = str(metadata.get("project", "") or "")
    if project == repo_name:
        return True

    repository_name = str(metadata.get("repository_name", "") or "")
    if repository_name == repo_name:
        return True

    path_value = str(metadata.get("path", "") or "")
    if path_value and repo_root is not None:
        try:
            path = Path(path_value)
            if path.is_absolute() and str(path).startswith(str(repo_root)):
                return True
        except (TypeError, ValueError):
            return False

    return False


def _resolve_matches(nodes: list[Any], target: str) -> list[Any]:
    scored: list[tuple[int, Any]] = []
    for node in nodes:
        score = _match_score(node, target)
        if score > 0:
            scored.append((score, node))
    scored.sort(key=lambda item: (-item[0], str(getattr(item[1], "name", ""))))
    if not scored:
        return []
    best_score = scored[0][0]
    return [node for score, node in scored if score == best_score]


def _match_score(node: Any, query: str) -> int:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return 0
    metadata = _metadata(node)
    node_name = str(getattr(node, "name", "") or "")
    candidates = {
        node_name,
        str(metadata.get("symbol", "") or ""),
        str(metadata.get("path", "") or ""),
        str(metadata.get("route_path", "") or ""),
        str(metadata.get("text", "") or ""),
        str(metadata.get("method", "") or ""),
        str(metadata.get("language", "") or ""),
        str(metadata.get("last_state", "") or ""),
        str(metadata.get("last_commit_summary", "") or ""),
        str(metadata.get("history_summary", "") or ""),
    }
    lowered = [candidate.lower() for candidate in candidates if candidate]
    if any(candidate == normalized_query for candidate in lowered):
        return 100
    if any(
        Path(candidate).name.lower() == normalized_query
        for candidate in candidates
        if candidate
    ):
        return 90
    if any(candidate.endswith(f"::{query}") for candidate in candidates if candidate):
        return 80
    if any(normalized_query in candidate for candidate in lowered):
        return 60
    return 0


def _serialize_node(node: Any) -> dict[str, Any]:
    metadata = _metadata(node)
    return {
        "id": str(getattr(node, "id")),
        "node_type": str(getattr(node, "node_type", "")),
        "name": str(getattr(node, "name", "")),
        "metadata": metadata,
    }


def _normalize_repository_remote(repo_url: str | None) -> str | None:
    if repo_url is None:
        return None
    raw_url = str(repo_url).strip()
    if not raw_url:
        return None
    if raw_url.startswith("git@"):
        host_and_path = raw_url[4:]
        if ":" in host_and_path:
            host, path = host_and_path.split(":", 1)
            normalized_path = path[:-4] if path.endswith(".git") else path
            return f"ssh://{host}/{normalized_path}"
    if raw_url.endswith(".git"):
        raw_url = raw_url[:-4]
    return raw_url.rstrip("/")


def _repo_matches_scopes(
    repository: Any,
    repo_path: str | None,
    allowed_repo_scopes: list[str] | None,
) -> bool:
    scopes = [
        scope.strip().rstrip("/")
        for scope in (allowed_repo_scopes or [])
        if scope and scope.strip()
    ]
    if not scopes or "*" in scopes:
        return True
    repo_name = str(getattr(repository, "repo_name", "") or "").strip()
    repo_url = _normalize_repository_remote(getattr(repository, "repo_url", None))
    candidates = {repo_name}
    if repo_path:
        repo_root = str(Path(repo_path).resolve()).rstrip("/")
        candidates.add(repo_root)
        candidates.add(Path(repo_root).name)
    if repo_url:
        candidates.add(repo_url)
    for scope in scopes:
        for candidate in candidates:
            if candidate == scope or candidate.startswith(f"{scope}/"):
                return True
    return False
