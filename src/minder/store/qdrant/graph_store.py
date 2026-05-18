"""Qdrant Graph Store — implements IGraphRepository using Qdrant collections."""

from __future__ import annotations
import uuid
from collections import deque
from typing import Any
from minder.store.qdrant.client import QdrantClientWrapper
from minder.store.qdrant.crud import CollectionCRUD, _Doc, _uid


class QdrantGraphStore:
    """Graph store backed by Qdrant. Two collections: graph_nodes, graph_edges."""

    def __init__(self, client: QdrantClientWrapper) -> None:
        self._client = client
        self._nodes = CollectionCRUD(client.client, f"{client.prefix}graph_nodes")
        self._edges = CollectionCRUD(client.client, f"{client.prefix}graph_edges")

    async def init_db(self) -> None:
        await self._nodes.ensure()
        await self._edges.ensure()

    async def dispose(self) -> None:
        await self._client.close()

    # -- Nodes --
    async def add_node(
        self,
        node_type: str,
        name: str,
        metadata: dict[str, Any] | None = None,
        node_id: uuid.UUID | None = None,
        *,
        repo_id: str = "",
        branch: str = "",
    ) -> Any:
        nid = _uid(node_id or uuid.uuid4())
        payload = {
            "node_type": node_type,
            "name": name,
            "extra_metadata": metadata or {},
            "repo_id": repo_id,
            "branch": branch,
        }
        return await self._nodes.insert(payload, nid)

    async def upsert_node(
        self,
        node_type: str,
        name: str,
        metadata: dict[str, Any] | None = None,
        *,
        repo_id: str = "",
        branch: str = "",
    ) -> Any:
        existing = await self._find_node(repo_id, branch, node_type, name)
        if existing:
            if metadata:
                merged = {
                    **dict(existing._data.get("extra_metadata") or {}),
                    **metadata,
                }
                await self._nodes.update(str(existing.id), {"extra_metadata": merged})
            return await self._nodes.get(str(existing.id))
        return await self.add_node(
            node_type, name, metadata, repo_id=repo_id, branch=branch
        )

    async def _find_node(
        self, repo_id: str, branch: str, node_type: str, name: str
    ) -> _Doc | None:
        docs = await self._nodes.find_many(
            {
                "repo_id": repo_id,
                "branch": branch,
                "node_type": node_type,
                "name": name,
            },
            limit=1,
        )
        return docs[0] if docs else None

    async def get_node(self, node_id: uuid.UUID) -> Any:
        return await self._nodes.get(_uid(node_id))

    async def get_node_by_name(
        self, node_type: str, name: str, *, repo_id: str = "", branch: str = ""
    ) -> Any:
        return await self._find_node(repo_id, branch, node_type, name)

    async def list_nodes(self) -> list[Any]:
        return await self._nodes.find_many()

    async def list_nodes_by_scope(
        self,
        *,
        repo_id: str,
        branch: str | None = None,
        node_types: set[str] | None = None,
    ) -> list[Any]:
        f: dict[str, Any] = {"repo_id": repo_id}
        if branch is not None:
            f["branch"] = branch
        nodes = await self._nodes.find_many(f)
        if node_types:
            nodes = [n for n in nodes if n._data.get("node_type") in node_types]
        return nodes

    async def list_edges(self) -> list[Any]:
        return await self._edges.find_many()

    async def list_edges_by_scope(self, *, repo_id: str) -> list[Any]:
        return await self._edges.find_many({"repo_id": repo_id})

    async def query_by_type(self, node_type: str, *, repo_id: str = "") -> list[Any]:
        f: dict[str, Any] = {"node_type": node_type}
        if repo_id:
            f["repo_id"] = repo_id
        return await self._nodes.find_many(f)

    async def _cascade_delete_edges(self, nid: str) -> None:
        """Delete all edges connected to a node using a targeted OR-filter."""
        edges = await self._edges.find_or([{"source_id": nid}, {"target_id": nid}])
        for e in edges:
            await self._edges.delete(str(e.id))

    async def delete_node(self, node_id: uuid.UUID) -> None:
        nid = _uid(node_id)
        await self._nodes.delete(nid)
        await self._cascade_delete_edges(nid)

    async def delete_nodes_by_scope(
        self, *, repo_id: str, branch: str | None = None, paths: set[str] | None = None
    ) -> int:
        f: dict[str, Any] = {"repo_id": repo_id}
        if branch is not None:
            f["branch"] = branch
        nodes = await self._nodes.find_many(f)
        to_delete = []
        for n in nodes:
            if paths is not None:
                meta = n._data.get("extra_metadata") or {}
                if str(meta.get("path", "") or "") in paths:
                    to_delete.append(str(n.id))
            else:
                to_delete.append(str(n.id))
        for nid in to_delete:
            await self._cascade_delete_edges(nid)
            await self._nodes.delete(nid)
        return len(to_delete)

    async def list_repo_branches(self, repo_id: str) -> list[str]:
        nodes = await self._nodes.find_many({"repo_id": repo_id})
        return list({n._data.get("branch", "") for n in nodes if n._data.get("branch")})

    # -- Edges --
    async def add_edge(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation: str,
        weight: float = 1.0,
        edge_id: uuid.UUID | None = None,
        *,
        repo_id: str = "",
    ) -> Any:
        eid = _uid(edge_id or uuid.uuid4())
        payload = {
            "source_id": _uid(source_id),
            "target_id": _uid(target_id),
            "relation": relation,
            "weight": weight,
            "repo_id": repo_id,
        }
        return await self._edges.insert(payload, eid)

    async def upsert_edge(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation: str,
        weight: float = 1.0,
        *,
        repo_id: str = "",
    ) -> Any:
        sid, tid = _uid(source_id), _uid(target_id)
        edges = await self._edges.find_many(
            {
                "repo_id": repo_id,
                "source_id": sid,
                "target_id": tid,
                "relation": relation,
            },
            limit=1,
        )
        if edges:
            await self._edges.update(str(edges[0].id), {"weight": weight})
            return await self._edges.get(str(edges[0].id))
        return await self.add_edge(
            source_id, target_id, relation, weight, repo_id=repo_id
        )

    async def delete_edge(self, edge_id: uuid.UUID) -> None:
        await self._edges.delete(_uid(edge_id))

    # -- Bulk --
    async def bulk_upsert_nodes(
        self, nodes: list[dict[str, Any]], *, repo_id: str, branch: str = ""
    ) -> dict[tuple[str, str], uuid.UUID]:
        id_map: dict[tuple[str, str], uuid.UUID] = {}
        for nd in nodes:
            node = await self.upsert_node(
                nd["node_type"],
                nd["name"],
                nd.get("metadata") or {},
                repo_id=repo_id,
                branch=branch,
            )
            id_map[(nd["node_type"], nd["name"])] = node.id
        return id_map

    async def bulk_upsert_edges(
        self, edges: list[dict[str, Any]], *, repo_id: str
    ) -> int:
        count = 0
        for ed in edges:
            await self.upsert_edge(
                ed["source_id"],
                ed["target_id"],
                ed["relation"],
                ed.get("weight", 1.0),
                repo_id=repo_id,
            )
            count += 1
        return count

    # -- Traversal --
    async def get_neighbors(
        self, node_id: uuid.UUID, *, direction: str = "out", relation: str | None = None
    ) -> list[Any]:
        nid = _uid(node_id)
        neighbor_ids: list[str] = []
        # Only fetch edges connected to this node, not the entire collection
        if direction == "out":
            edges = await self._edges.find_many({"source_id": nid})
        elif direction == "in":
            edges = await self._edges.find_many({"target_id": nid})
        else:  # "both"
            edges = await self._edges.find_or([{"source_id": nid}, {"target_id": nid}])
        for e in edges:
            if relation and e._data.get("relation") != relation:
                continue
            if direction in ("out", "both") and e._data.get("source_id") == nid:
                neighbor_ids.append(e._data["target_id"])
            if direction in ("in", "both") and e._data.get("target_id") == nid:
                neighbor_ids.append(e._data["source_id"])
        seen: set[str] = set()
        unique = [i for i in neighbor_ids if not (i in seen or seen.add(i))]  # type: ignore[func-returns-value]
        results = []
        for uid_str in unique:
            n = await self._nodes.get(uid_str)
            if n:
                results.append(n)
        return results

    async def get_path(
        self, source_id: uuid.UUID, target_id: uuid.UUID, *, max_depth: int = 6
    ) -> list[Any]:
        if source_id == target_id:
            n = await self.get_node(source_id)
            return [n] if n else []
        sid, tid = _uid(source_id), _uid(target_id)
        visited: set[str] = {sid}
        queue: deque[tuple[str, list[str]]] = deque([(sid, [sid])])
        all_edges = await self._edges.find_many()
        edge_map: dict[str, list[str]] = {}
        for e in all_edges:
            s = e._data.get("source_id", "")
            t = e._data.get("target_id", "")
            edge_map.setdefault(s, []).append(t)
        while queue:
            cur, path = queue.popleft()
            if len(path) > max_depth:
                continue
            for nb in edge_map.get(cur, []):
                if nb == tid:
                    full = path + [tid]
                    return [n for pid in full if (n := await self._nodes.get(pid))]
                if nb not in visited:
                    visited.add(nb)
                    queue.append((nb, path + [nb]))
        return []

    async def get_neighborhood(
        self, node_id: uuid.UUID, *, max_depth: int = 4, max_nodes: int = 100
    ) -> tuple[list[Any], list[Any]]:
        nodes_map: dict[str, _Doc] = {}
        edges_seen: set[str] = set()
        edges_list: list[_Doc] = []
        current: set[str] = {_uid(node_id)}
        visited: set[str] = set()
        all_edges = await self._edges.find_many()
        for depth in range(max_depth + 1):
            if not current or len(nodes_map) >= max_nodes:
                break
            for nid in list(current):
                if nid not in nodes_map and len(nodes_map) < max_nodes:
                    n = await self._nodes.get(nid)
                    if n:
                        nodes_map[nid] = n
            if depth < max_depth:
                next_level: set[str] = set()
                for e in all_edges:
                    s, t = e._data.get("source_id", ""), e._data.get("target_id", "")
                    if s in current or t in current:
                        eid = str(e._data.get("id", id(e)))
                        if eid not in edges_seen:
                            edges_seen.add(eid)
                            edges_list.append(e)
                        next_level.add(s)
                        next_level.add(t)
                visited.update(current)
                current = next_level - visited
        final_ids = set(nodes_map.keys())
        final_edges = [
            e
            for e in edges_list
            if e._data.get("source_id") in final_ids
            and e._data.get("target_id") in final_ids
        ]
        return list(nodes_map.values()), final_edges
