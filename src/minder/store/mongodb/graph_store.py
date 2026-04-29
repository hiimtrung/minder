"""
MongoGraphStore — MongoDB-backed implementation of IGraphRepository.

Drop-in replacement for KnowledgeGraphStore so the graph store can live
in the same MongoDB instance as the operational store instead of a separate
SQLite file.
"""

from __future__ import annotations

import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING

from minder.store.mongodb.client import MongoClient


def _now() -> datetime:
    return datetime.now(UTC)


class _NodeDoc:
    """Attribute wrapper for a graph_nodes MongoDB document."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def id(self) -> uuid.UUID:
        return uuid.UUID(str(self._data.get("_id") or self._data.get("id", "")))

    @property
    def repo_id(self) -> str:
        return str(self._data.get("repo_id", ""))

    @property
    def branch(self) -> str:
        return str(self._data.get("branch", ""))

    @property
    def node_type(self) -> str:
        return str(self._data.get("node_type", ""))

    @property
    def name(self) -> str:
        return str(self._data.get("name", ""))

    @property
    def extra_metadata(self) -> dict[str, Any]:
        return dict(self._data.get("extra_metadata") or {})

    @extra_metadata.setter
    def extra_metadata(self, value: dict[str, Any]) -> None:
        self._data["extra_metadata"] = value

    @property
    def created_at(self) -> datetime | None:
        return self._data.get("created_at")

    def __repr__(self) -> str:
        return f"_NodeDoc(id={self.id!r}, type={self.node_type!r}, name={self.name!r})"


class _EdgeDoc:
    """Attribute wrapper for a graph_edges MongoDB document."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def id(self) -> uuid.UUID:
        return uuid.UUID(str(self._data.get("_id") or self._data.get("id", "")))

    @property
    def repo_id(self) -> str:
        return str(self._data.get("repo_id", ""))

    @property
    def source_id(self) -> uuid.UUID:
        return uuid.UUID(str(self._data["source_id"]))

    @property
    def target_id(self) -> uuid.UUID:
        return uuid.UUID(str(self._data["target_id"]))

    @property
    def relation(self) -> str:
        return str(self._data.get("relation", ""))

    @property
    def weight(self) -> float:
        return float(self._data.get("weight", 1.0))

    @property
    def created_at(self) -> datetime | None:
        return self._data.get("created_at")

    def __repr__(self) -> str:
        return f"_EdgeDoc(id={self.id!r}, rel={self.relation!r})"


class MongoGraphStore:
    """
    MongoDB-backed graph store.

    Collections:
      graph_nodes — (repo_id, branch, node_type, name) unique
      graph_edges — (repo_id, source_id, target_id, relation) unique
    """

    def __init__(self, client: MongoClient) -> None:
        self._client = client
        self._db: AsyncIOMotorDatabase = client.db  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init_db(self) -> None:
        nodes = self._db["graph_nodes"]
        await nodes.create_index(
            [("repo_id", ASCENDING), ("branch", ASCENDING), ("node_type", ASCENDING), ("name", ASCENDING)],
            unique=True,
            name="uq_graph_node_repo_branch_type_name",
        )
        await nodes.create_index([("repo_id", ASCENDING)])
        await nodes.create_index([("branch", ASCENDING)])
        await nodes.create_index([("node_type", ASCENDING)])

        edges = self._db["graph_edges"]
        await edges.create_index(
            [("repo_id", ASCENDING), ("source_id", ASCENDING), ("target_id", ASCENDING), ("relation", ASCENDING)],
            unique=True,
            name="uq_graph_edge_repo_src_tgt_rel",
        )
        await edges.create_index([("repo_id", ASCENDING)])
        await edges.create_index([("source_id", ASCENDING)])
        await edges.create_index([("target_id", ASCENDING)])

    async def dispose(self) -> None:
        await self._client.close()

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    async def add_node(
        self,
        node_type: str,
        name: str,
        metadata: dict[str, Any] | None = None,
        node_id: uuid.UUID | None = None,
        *,
        repo_id: str = "",
        branch: str = "",
    ) -> _NodeDoc:
        nid = str(node_id or uuid.uuid4())
        doc = {
            "_id": nid,
            "repo_id": repo_id,
            "branch": branch,
            "node_type": node_type,
            "name": name,
            "extra_metadata": metadata or {},
            "created_at": _now(),
        }
        await self._db["graph_nodes"].insert_one(doc)
        return _NodeDoc(doc)

    async def upsert_node(
        self,
        node_type: str,
        name: str,
        metadata: dict[str, Any] | None = None,
        *,
        repo_id: str = "",
        branch: str = "",
    ) -> _NodeDoc:
        filter_ = {"repo_id": repo_id, "branch": branch, "node_type": node_type, "name": name}
        update: dict[str, Any] = {
            "$setOnInsert": {"_id": str(uuid.uuid4()), "created_at": _now(), "extra_metadata": {}},
            "$set": {"repo_id": repo_id, "branch": branch, "node_type": node_type, "name": name},
        }
        if metadata:
            update["$set"]["extra_metadata"] = metadata
        result = await self._db["graph_nodes"].find_one_and_update(
            filter_,
            update,
            upsert=True,
            return_document=True,
        )
        return _NodeDoc(result)

    async def get_node(self, node_id: uuid.UUID) -> _NodeDoc | None:
        doc = await self._db["graph_nodes"].find_one({"_id": str(node_id)})
        return _NodeDoc(doc) if doc else None

    async def get_node_by_name(
        self,
        node_type: str,
        name: str,
        *,
        repo_id: str = "",
        branch: str = "",
    ) -> _NodeDoc | None:
        doc = await self._db["graph_nodes"].find_one(
            {"repo_id": repo_id, "branch": branch, "node_type": node_type, "name": name}
        )
        return _NodeDoc(doc) if doc else None

    async def list_nodes(self) -> list[_NodeDoc]:
        return [_NodeDoc(doc) async for doc in self._db["graph_nodes"].find({})]

    async def list_nodes_by_scope(
        self,
        *,
        repo_id: str,
        branch: str | None = None,
        node_types: set[str] | None = None,
    ) -> list[_NodeDoc]:
        q: dict[str, Any] = {"repo_id": repo_id}
        if branch is not None:
            q["branch"] = branch
        if node_types:
            q["node_type"] = {"$in": list(node_types)}
        return [_NodeDoc(doc) async for doc in self._db["graph_nodes"].find(q)]

    async def list_edges(self) -> list[_EdgeDoc]:
        return [_EdgeDoc(doc) async for doc in self._db["graph_edges"].find({})]

    async def list_edges_by_scope(self, *, repo_id: str) -> list[_EdgeDoc]:
        return [_EdgeDoc(doc) async for doc in self._db["graph_edges"].find({"repo_id": repo_id})]

    async def query_by_type(self, node_type: str, *, repo_id: str = "") -> list[_NodeDoc]:
        q: dict[str, Any] = {"node_type": node_type}
        if repo_id:
            q["repo_id"] = repo_id
        return [_NodeDoc(doc) async for doc in self._db["graph_nodes"].find(q)]

    async def delete_node(self, node_id: uuid.UUID) -> None:
        nid = str(node_id)
        await self._db["graph_nodes"].delete_one({"_id": nid})
        await self._db["graph_edges"].delete_many(
            {"$or": [{"source_id": nid}, {"target_id": nid}]}
        )

    async def delete_nodes_by_scope(
        self,
        *,
        repo_id: str,
        branch: str | None = None,
        paths: set[str] | None = None,
    ) -> int:
        q: dict[str, Any] = {"repo_id": repo_id}
        if branch is not None:
            q["branch"] = branch

        if paths is not None:
            ids: list[str] = []
            async for doc in self._db["graph_nodes"].find(q, {"_id": 1, "extra_metadata": 1}):
                meta = doc.get("extra_metadata") or {}
                if str(meta.get("path", "") or "") in paths:
                    ids.append(str(doc["_id"]))
            if not ids:
                return 0
            await self._db["graph_edges"].delete_many(
                {"$or": [{"source_id": {"$in": ids}}, {"target_id": {"$in": ids}}]}
            )
            result = await self._db["graph_nodes"].delete_many({"_id": {"$in": ids}})
            return result.deleted_count

        # Full scope deletion — collect IDs first for edge cascade
        ids = [str(doc["_id"]) async for doc in self._db["graph_nodes"].find(q, {"_id": 1})]
        if ids:
            await self._db["graph_edges"].delete_many(
                {"$or": [{"source_id": {"$in": ids}}, {"target_id": {"$in": ids}}]}
            )
        result = await self._db["graph_nodes"].delete_many(q)
        return result.deleted_count

    async def list_repo_branches(self, repo_id: str) -> list[str]:
        values = await self._db["graph_nodes"].distinct("branch", {"repo_id": repo_id})
        return [str(b) for b in values if b]

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    async def add_edge(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation: str,
        weight: float = 1.0,
        edge_id: uuid.UUID | None = None,
        *,
        repo_id: str = "",
    ) -> _EdgeDoc:
        eid = str(edge_id or uuid.uuid4())
        doc = {
            "_id": eid,
            "repo_id": repo_id,
            "source_id": str(source_id),
            "target_id": str(target_id),
            "relation": relation,
            "weight": weight,
            "created_at": _now(),
        }
        await self._db["graph_edges"].insert_one(doc)
        return _EdgeDoc(doc)

    async def upsert_edge(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation: str,
        weight: float = 1.0,
        *,
        repo_id: str = "",
    ) -> _EdgeDoc:
        filter_ = {
            "repo_id": repo_id,
            "source_id": str(source_id),
            "target_id": str(target_id),
            "relation": relation,
        }
        update: dict[str, Any] = {
            "$setOnInsert": {"_id": str(uuid.uuid4()), "created_at": _now()},
            "$set": {**filter_, "weight": weight},
        }
        result = await self._db["graph_edges"].find_one_and_update(
            filter_,
            update,
            upsert=True,
            return_document=True,
        )
        return _EdgeDoc(result)

    async def delete_edge(self, edge_id: uuid.UUID) -> None:
        await self._db["graph_edges"].delete_one({"_id": str(edge_id)})

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    async def bulk_upsert_nodes(
        self,
        nodes: list[dict[str, Any]],
        *,
        repo_id: str,
        branch: str = "",
    ) -> dict[tuple[str, str], uuid.UUID]:
        id_map: dict[tuple[str, str], uuid.UUID] = {}
        for node_data in nodes:
            node_type = node_data["node_type"]
            name = node_data["name"]
            node = await self.upsert_node(
                node_type, name, node_data.get("metadata") or {}, repo_id=repo_id, branch=branch
            )
            id_map[(node_type, name)] = node.id
        return id_map

    async def bulk_upsert_edges(
        self,
        edges: list[dict[str, Any]],
        *,
        repo_id: str,
    ) -> int:
        count = 0
        for edge_data in edges:
            await self.upsert_edge(
                edge_data["source_id"],
                edge_data["target_id"],
                edge_data["relation"],
                edge_data.get("weight", 1.0),
                repo_id=repo_id,
            )
            count += 1
        return count

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    async def get_neighbors(
        self,
        node_id: uuid.UUID,
        *,
        direction: str = "out",
        relation: str | None = None,
    ) -> list[_NodeDoc]:
        nid = str(node_id)
        neighbor_strs: list[str] = []

        async def _collect(q: dict[str, Any], field: str) -> list[str]:
            if relation:
                q["relation"] = relation
            return [str(doc[field]) async for doc in self._db["graph_edges"].find(q, {field: 1})]

        if direction in ("out", "both"):
            neighbor_strs.extend(await _collect({"source_id": nid}, "target_id"))
        if direction in ("in", "both"):
            neighbor_strs.extend(await _collect({"target_id": nid}, "source_id"))

        seen: set[str] = set()
        unique = [i for i in neighbor_strs if not (i in seen or seen.add(i))]  # type: ignore[func-returns-value]
        if not unique:
            return []
        return [_NodeDoc(doc) async for doc in self._db["graph_nodes"].find({"_id": {"$in": unique}})]

    async def get_path(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        *,
        max_depth: int = 6,
    ) -> list[_NodeDoc]:
        if source_id == target_id:
            node = await self.get_node(source_id)
            return [node] if node else []

        t_str = str(target_id)
        visited: set[str] = {str(source_id)}
        queue: deque[tuple[str, list[str]]] = deque([(str(source_id), [str(source_id)])])

        while queue:
            current_id, path = queue.popleft()
            if len(path) > max_depth:
                continue
            neighbors = [
                str(doc["target_id"])
                async for doc in self._db["graph_edges"].find({"source_id": current_id}, {"target_id": 1})
            ]
            for nid in neighbors:
                if nid == t_str:
                    full_path = path + [t_str]
                    result: list[_NodeDoc] = []
                    for pid in full_path:
                        doc = await self._db["graph_nodes"].find_one({"_id": pid})
                        if doc:
                            result.append(_NodeDoc(doc))
                    return result
                if nid not in visited:
                    visited.add(nid)
                    queue.append((nid, path + [nid]))
        return []

    async def get_neighborhood(
        self,
        node_id: uuid.UUID,
        *,
        max_depth: int = 4,
        max_nodes: int = 100,
    ) -> tuple[list[_NodeDoc], list[_EdgeDoc]]:
        nodes_map: dict[str, _NodeDoc] = {}
        edges_map: dict[str, _EdgeDoc] = {}
        current_level: set[str] = {str(node_id)}
        visited: set[str] = set()

        for depth in range(max_depth + 1):
            if not current_level or len(nodes_map) >= max_nodes:
                break

            to_fetch = [nid for nid in current_level if nid not in nodes_map]
            if to_fetch:
                async for doc in self._db["graph_nodes"].find({"_id": {"$in": to_fetch}}):
                    if len(nodes_map) < max_nodes:
                        nodes_map[str(doc["_id"])] = _NodeDoc(doc)

            if depth < max_depth:
                next_level: set[str] = set()
                async for doc in self._db["graph_edges"].find({
                    "$or": [
                        {"source_id": {"$in": list(current_level)}},
                        {"target_id": {"$in": list(current_level)}},
                    ]
                }):
                    edges_map[str(doc["_id"])] = _EdgeDoc(doc)
                    next_level.add(str(doc["source_id"]))
                    next_level.add(str(doc["target_id"]))
                visited.update(current_level)
                current_level = next_level - visited

        final_ids = set(nodes_map.keys())
        final_edges = [
            e for e in edges_map.values()
            if str(e.source_id) in final_ids and str(e.target_id) in final_ids
        ]
        return list(nodes_map.values()), final_edges
