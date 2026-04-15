from __future__ import annotations

from collections import Counter, deque
from pathlib import Path
from typing import Any

from minder.store.interfaces import IGraphRepository


class GraphTools:
    def __init__(self, graph_store: IGraphRepository | None) -> None:
        self._graph_store = graph_store

    async def list_repo_nodes(
        self,
        *,
        repo_id: str | None = None,
        repo_name: str | None = None,
        repo_path: str | None = None,
    ) -> tuple[str, list[Any]]:
        if self._graph_store is None:
            raise RuntimeError("Graph store is not configured")

        effective_repo_name, repo_root = _resolve_repo_identity(
            repo_name=repo_name,
            repo_path=repo_path,
        )
        all_nodes = await self._graph_store.list_nodes()
        repo_nodes = [
            node
            for node in all_nodes
            if _node_belongs_to_repo(
                node,
                repo_id=repo_id,
                repo_name=effective_repo_name,
                repo_root=repo_root,
            )
        ]
        return effective_repo_name, repo_nodes

    async def minder_search_graph(
        self,
        query: str,
        *,
        repo_path: str | None = None,
        repo_id: str | None = None,
        repo_name: str | None = None,
        node_types: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        if self._graph_store is None:
            raise RuntimeError("Graph store is not configured")

        effective_repo_name, repo_nodes = await self.list_repo_nodes(
            repo_id=repo_id,
            repo_name=repo_name,
            repo_path=repo_path,
        )
        allowed_types = {node_type.strip() for node_type in (node_types or []) if node_type.strip()}

        matches: list[dict[str, Any]] = []
        for node in repo_nodes:
            node_type = str(getattr(node, "node_type", ""))
            if allowed_types and node_type not in allowed_types:
                continue
            score = _match_score(node, query)
            if score <= 0:
                continue
            item = _serialize_node(node)
            item["score"] = score
            matches.append(item)

        matches.sort(key=lambda item: (-int(item["score"]), item["node_type"], item["name"]))
        limited = matches[: max(1, limit)]
        return {
            "query": query,
            "repo_name": effective_repo_name,
            "filters": {"node_types": sorted(allowed_types)},
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
        depth: int = 2,
        limit: int = 25,
    ) -> dict[str, Any]:
        if self._graph_store is None:
            raise RuntimeError("Graph store is not configured")

        effective_repo_name, repo_nodes = await self.list_repo_nodes(
            repo_id=repo_id,
            repo_name=repo_name,
            repo_path=repo_path,
        )
        matches = _resolve_matches(repo_nodes, target)
        seed_nodes = matches[: min(5, max(1, limit))]

        if not seed_nodes:
            return {
                "target": target,
                "repo_name": effective_repo_name,
                "matches": [],
                "impacted": [],
                "summary": {
                    "match_count": 0,
                    "impacted_count": 0,
                    "upstream_count": 0,
                    "downstream_count": 0,
                    "by_node_type": {},
                },
            }

        repo_node_ids = {getattr(node, "id") for node in repo_nodes}
        visited = {getattr(node, "id") for node in seed_nodes}
        queue: deque[tuple[Any, int]] = deque((getattr(node, "id"), 0) for node in seed_nodes)
        impacted: list[dict[str, Any]] = []
        type_counter: Counter[str] = Counter()
        upstream_count = 0
        downstream_count = 0

        while queue and len(impacted) < limit:
            node_id, current_depth = queue.popleft()
            if current_depth >= max(1, depth):
                continue

            for direction in ("out", "in"):
                neighbors = await self._graph_store.get_neighbors(node_id, direction=direction)
                for neighbor in neighbors:
                    neighbor_id = getattr(neighbor, "id")
                    if neighbor_id not in repo_node_ids or neighbor_id in visited:
                        continue
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, current_depth + 1))
                    serialized = _serialize_node(neighbor)
                    serialized["direction"] = "downstream" if direction == "out" else "upstream"
                    serialized["distance"] = current_depth + 1
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

        return {
            "target": target,
            "repo_name": effective_repo_name,
            "matches": [_serialize_node(node) for node in seed_nodes],
            "impacted": impacted,
            "summary": {
                "match_count": len(seed_nodes),
                "impacted_count": len(impacted),
                "upstream_count": upstream_count,
                "downstream_count": downstream_count,
                "by_node_type": dict(type_counter),
            },
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
) -> bool:
    metadata = _metadata(node)
    if repo_id and str(metadata.get("repo_id", "") or "") == repo_id:
        return True

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
    }
    lowered = [candidate.lower() for candidate in candidates if candidate]
    if any(candidate == normalized_query for candidate in lowered):
        return 100
    if any(Path(candidate).name.lower() == normalized_query for candidate in candidates if candidate):
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