"""
KnowledgeGraphStore — SQLAlchemy-backed graph store for module/service/owner
relationships.

Nodes represent named entities (module, file, service, owner).
Edges represent directed relationships (depends_on, imports, calls, owns).

Backed by SQLite (dev) or PostgreSQL (prod) via the shared async engine.
"""

from __future__ import annotations

import uuid
from collections import deque
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from minder.models import Base, GraphEdge, GraphNode


class KnowledgeGraphStore:
    """Async graph store. Supports node/edge CRUD + BFS traversal."""

    def __init__(self, db_url: str, echo: bool = False) -> None:
        self._engine = create_async_engine(db_url, echo=echo)
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init_db(self) -> None:
        """Create graph tables (idempotent)."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self._engine.dispose()

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._session_factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    async def add_node(
        self,
        node_type: str,
        name: str,
        metadata: dict[str, Any] | None = None,
        node_id: uuid.UUID | None = None,
    ) -> GraphNode:
        """Insert a node. Raises on duplicate (type, name)."""
        async with self._session() as sess:
            node = GraphNode(
                id=node_id or uuid.uuid4(),
                node_type=node_type,
                name=name,
                node_metadata=metadata or {},
            )
            sess.add(node)
            await sess.flush()
            await sess.refresh(node)
            return node

    async def upsert_node(
        self,
        node_type: str,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> GraphNode:
        """Insert or update a node by (type, name). Returns the persisted node."""
        async with self._session() as sess:
            result = await sess.execute(
                select(GraphNode).where(
                    GraphNode.node_type == node_type, GraphNode.name == name
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                if metadata:
                    await sess.execute(
                        update(GraphNode)
                        .where(GraphNode.id == existing.id)
                        .values(node_metadata={**dict(existing.node_metadata), **metadata})
                    )
                    await sess.refresh(existing)
                return existing
            node = GraphNode(
                id=uuid.uuid4(),
                node_type=node_type,
                name=name,
                node_metadata=metadata or {},
            )
            sess.add(node)
            await sess.flush()
            await sess.refresh(node)
            return node

    async def get_node(self, node_id: uuid.UUID) -> GraphNode | None:
        async with self._session() as sess:
            result = await sess.execute(
                select(GraphNode).where(GraphNode.id == node_id)
            )
            return result.scalar_one_or_none()

    async def get_node_by_name(self, node_type: str, name: str) -> GraphNode | None:
        async with self._session() as sess:
            result = await sess.execute(
                select(GraphNode).where(
                    GraphNode.node_type == node_type, GraphNode.name == name
                )
            )
            return result.scalar_one_or_none()

    async def query_by_type(self, node_type: str) -> list[GraphNode]:
        async with self._session() as sess:
            result = await sess.execute(
                select(GraphNode).where(GraphNode.node_type == node_type)
            )
            return list(result.scalars().all())

    async def delete_node(self, node_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(GraphNode).where(GraphNode.id == node_id))
            # Cascade: remove all edges incident to this node
            await sess.execute(
                delete(GraphEdge).where(
                    (GraphEdge.source_id == node_id) | (GraphEdge.target_id == node_id)
                )
            )

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
    ) -> GraphEdge:
        """Insert a directed edge. Raises on duplicate (source, target, relation)."""
        async with self._session() as sess:
            edge = GraphEdge(
                id=edge_id or uuid.uuid4(),
                source_id=source_id,
                target_id=target_id,
                relation=relation,
                weight=weight,
            )
            sess.add(edge)
            await sess.flush()
            await sess.refresh(edge)
            return edge

    async def upsert_edge(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation: str,
        weight: float = 1.0,
    ) -> GraphEdge:
        """Insert or update edge by (source, target, relation)."""
        async with self._session() as sess:
            result = await sess.execute(
                select(GraphEdge).where(
                    GraphEdge.source_id == source_id,
                    GraphEdge.target_id == target_id,
                    GraphEdge.relation == relation,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                await sess.execute(
                    update(GraphEdge)
                    .where(GraphEdge.id == existing.id)
                    .values(weight=weight)
                )
                await sess.refresh(existing)
                return existing
            edge = GraphEdge(
                id=uuid.uuid4(),
                source_id=source_id,
                target_id=target_id,
                relation=relation,
                weight=weight,
            )
            sess.add(edge)
            await sess.flush()
            await sess.refresh(edge)
            return edge

    async def delete_edge(self, edge_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(GraphEdge).where(GraphEdge.id == edge_id))

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    async def get_neighbors(
        self,
        node_id: uuid.UUID,
        *,
        direction: str = "out",
        relation: str | None = None,
    ) -> list[GraphNode]:
        """
        Return neighbor nodes.

        direction:
          "out"  — nodes that ``node_id`` points to   (source → target)
          "in"   — nodes that point to ``node_id``    (target ← source)
          "both" — union of out and in
        """
        async with self._session() as sess:
            neighbor_ids: list[uuid.UUID] = []

            async def _out() -> list[uuid.UUID]:
                stmt = select(GraphEdge.target_id).where(
                    GraphEdge.source_id == node_id
                )
                if relation:
                    stmt = stmt.where(GraphEdge.relation == relation)
                r = await sess.execute(stmt)
                return list(r.scalars().all())

            async def _in() -> list[uuid.UUID]:
                stmt = select(GraphEdge.source_id).where(
                    GraphEdge.target_id == node_id
                )
                if relation:
                    stmt = stmt.where(GraphEdge.relation == relation)
                r = await sess.execute(stmt)
                return list(r.scalars().all())

            if direction in ("out", "both"):
                neighbor_ids.extend(await _out())
            if direction in ("in", "both"):
                neighbor_ids.extend(await _in())

            if not neighbor_ids:
                return []

            seen: set[uuid.UUID] = set()
            unique_ids = [nid for nid in neighbor_ids if not (nid in seen or seen.add(nid))]  # type: ignore[func-returns-value]

            result = await sess.execute(
                select(GraphNode).where(GraphNode.id.in_(unique_ids))
            )
            return list(result.scalars().all())

    async def get_path(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        *,
        max_depth: int = 6,
    ) -> list[GraphNode]:
        """
        BFS shortest path from source to target following outgoing edges.
        Returns ordered list of nodes including source and target, or empty
        list if no path exists within max_depth.
        """
        if source_id == target_id:
            node = await self.get_node(source_id)
            return [node] if node else []

        visited: set[uuid.UUID] = {source_id}
        queue: deque[tuple[uuid.UUID, list[uuid.UUID]]] = deque(
            [(source_id, [source_id])]
        )

        while queue:
            current_id, path = queue.popleft()
            if len(path) > max_depth:
                continue
            async with self._session() as sess:
                result = await sess.execute(
                    select(GraphEdge.target_id).where(GraphEdge.source_id == current_id)
                )
                neighbors = list(result.scalars().all())

            for nid in neighbors:
                if nid == target_id:
                    full_path = path + [target_id]
                    nodes: list[GraphNode] = []
                    async with self._session() as sess:
                        for pid in full_path:
                            r = await sess.execute(
                                select(GraphNode).where(GraphNode.id == pid)
                            )
                            n = r.scalar_one_or_none()
                            if n:
                                nodes.append(n)
                    return nodes
                if nid not in visited:
                    visited.add(nid)
                    queue.append((nid, path + [nid]))

        return []
