"""
KnowledgeGraphStore — SQLAlchemy-backed graph store for module/service/owner
relationships.

Nodes represent named entities (module, file, service, owner).
Edges represent directed relationships (depends_on, imports, calls, owns).

v2 adds repo_id + branch columns so nodes from different repos/branches
never collide.  KnowledgeGraphStore.init_db() runs _migrate_graph_v2()
automatically on first boot when the columns are absent.

Backed by SQLite (dev) or PostgreSQL (prod) via the shared async engine.
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from minder.models import Base, GraphEdge, GraphNode

logger = logging.getLogger(__name__)


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
        """Create graph tables (idempotent) then run v2 migration if needed."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await self._migrate_graph_v2()

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
    # v2 schema migration
    # ------------------------------------------------------------------

    async def _migrate_graph_v2(self) -> None:
        """Add repo_id + branch columns and update unique constraints if missing."""
        async with self._engine.begin() as conn:
            dialect = conn.dialect.name  # type: ignore[attr-defined]

            if dialect == "sqlite":
                await self._migrate_graph_v2_sqlite(conn)
            elif dialect == "postgresql":
                await self._migrate_graph_v2_postgresql(conn)
            # Other dialects: no-op (create_all already built the new schema)

    async def _migrate_graph_v2_sqlite(self, conn: Any) -> None:
        """SQLite migration: recreate graph_nodes/graph_edges with new schema."""
        result = await conn.execute(text("PRAGMA table_info(graph_nodes)"))
        existing_cols = {row[1] for row in result.fetchall()}

        if "repo_id" not in existing_cols:
            logger.info("Migrating graph_nodes to v2 schema (SQLite)...")
            # Recreate graph_nodes with new columns + new unique constraint
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS graph_nodes_v2 (
                    id TEXT NOT NULL,
                    repo_id TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    node_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    metadata JSON,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    UNIQUE (repo_id, branch, node_type, name)
                )
            """))
            # Migrate existing data: extract repo_id/branch from JSON metadata
            await conn.execute(text("""
                INSERT OR IGNORE INTO graph_nodes_v2
                    (id, repo_id, branch, node_type, name, metadata, created_at)
                SELECT
                    id,
                    COALESCE(json_extract(metadata, '$.repo_id'), ''),
                    COALESCE(json_extract(metadata, '$.branch'), ''),
                    node_type,
                    name,
                    metadata,
                    created_at
                FROM graph_nodes
            """))
            await conn.execute(text("DROP TABLE graph_nodes"))
            await conn.execute(text("ALTER TABLE graph_nodes_v2 RENAME TO graph_nodes"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_graph_nodes_repo_id ON graph_nodes (repo_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_graph_nodes_branch ON graph_nodes (branch)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_graph_nodes_node_type ON graph_nodes (node_type)"
            ))
            logger.info("graph_nodes v2 migration complete.")

        # --- graph_edges ---
        result = await conn.execute(text("PRAGMA table_info(graph_edges)"))
        existing_edge_cols = {row[1] for row in result.fetchall()}

        if "repo_id" not in existing_edge_cols:
            logger.info("Migrating graph_edges to v2 schema (SQLite)...")
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS graph_edges_v2 (
                    id TEXT NOT NULL,
                    repo_id TEXT NOT NULL DEFAULT '',
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    UNIQUE (repo_id, source_id, target_id, relation)
                )
            """))
            await conn.execute(text("""
                INSERT OR IGNORE INTO graph_edges_v2
                    (id, repo_id, source_id, target_id, relation, weight, created_at)
                SELECT id, '', source_id, target_id, relation, weight, created_at
                FROM graph_edges
            """))
            await conn.execute(text("DROP TABLE graph_edges"))
            await conn.execute(text("ALTER TABLE graph_edges_v2 RENAME TO graph_edges"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_graph_edges_repo_id ON graph_edges (repo_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_graph_edges_source_id ON graph_edges (source_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_graph_edges_target_id ON graph_edges (target_id)"
            ))
            logger.info("graph_edges v2 migration complete.")

        # Migrate tracked_branches column on repositories table if missing
        result = await conn.execute(text("PRAGMA table_info(repositories)"))
        repo_cols = {row[1] for row in result.fetchall()}
        if "tracked_branches" not in repo_cols:
            await conn.execute(text(
                "ALTER TABLE repositories ADD COLUMN tracked_branches JSON DEFAULT '[]'"
            ))
            logger.info("repositories.tracked_branches column added.")

    async def _migrate_graph_v2_postgresql(self, conn: Any) -> None:
        """PostgreSQL migration: ADD COLUMN IF NOT EXISTS + constraint update."""
        # Check if repo_id column exists
        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'graph_nodes' AND column_name = 'repo_id'
        """))
        if not result.fetchone():
            logger.info("Migrating graph_nodes to v2 schema (PostgreSQL)...")
            await conn.execute(text(
                "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS repo_id VARCHAR NOT NULL DEFAULT ''"
            ))
            await conn.execute(text(
                "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS branch VARCHAR NOT NULL DEFAULT ''"
            ))
            # Populate from existing JSON metadata
            await conn.execute(text("""
                UPDATE graph_nodes
                SET repo_id = COALESCE(metadata->>'repo_id', ''),
                    branch  = COALESCE(metadata->>'branch', '')
                WHERE repo_id = '' OR repo_id IS NULL
            """))
            # Drop old constraint, add new
            await conn.execute(text(
                "ALTER TABLE graph_nodes DROP CONSTRAINT IF EXISTS uq_graph_node_type_name"
            ))
            await conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_graph_node_repo_branch_type_name
                ON graph_nodes (repo_id, branch, node_type, name)
            """))
            logger.info("graph_nodes v2 migration complete.")

        # --- graph_edges ---
        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'graph_edges' AND column_name = 'repo_id'
        """))
        if not result.fetchone():
            logger.info("Migrating graph_edges to v2 schema (PostgreSQL)...")
            await conn.execute(text(
                "ALTER TABLE graph_edges ADD COLUMN IF NOT EXISTS repo_id VARCHAR NOT NULL DEFAULT ''"
            ))
            await conn.execute(text(
                "ALTER TABLE graph_edges DROP CONSTRAINT IF EXISTS uq_graph_edge_src_tgt_rel"
            ))
            await conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_graph_edge_repo_src_tgt_rel
                ON graph_edges (repo_id, source_id, target_id, relation)
            """))
            logger.info("graph_edges v2 migration complete.")

        # tracked_branches on repositories
        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'repositories' AND column_name = 'tracked_branches'
        """))
        if not result.fetchone():
            await conn.execute(text(
                "ALTER TABLE repositories ADD COLUMN IF NOT EXISTS tracked_branches JSON DEFAULT '[]'"
            ))
            logger.info("repositories.tracked_branches column added.")

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
    ) -> GraphNode:
        """Insert a node. Raises on duplicate (repo_id, branch, type, name)."""
        async with self._session() as sess:
            node = GraphNode(
                id=node_id or uuid.uuid4(),
                repo_id=repo_id,
                branch=branch,
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
        *,
        repo_id: str = "",
        branch: str = "",
    ) -> GraphNode:
        """Insert or update a node by (repo_id, branch, type, name)."""
        async with self._session() as sess:
            result = await sess.execute(
                select(GraphNode).where(
                    GraphNode.repo_id == repo_id,
                    GraphNode.branch == branch,
                    GraphNode.node_type == node_type,
                    GraphNode.name == name,
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
                repo_id=repo_id,
                branch=branch,
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

    async def get_node_by_name(
        self,
        node_type: str,
        name: str,
        *,
        repo_id: str = "",
        branch: str = "",
    ) -> GraphNode | None:
        async with self._session() as sess:
            result = await sess.execute(
                select(GraphNode).where(
                    GraphNode.repo_id == repo_id,
                    GraphNode.branch == branch,
                    GraphNode.node_type == node_type,
                    GraphNode.name == name,
                )
            )
            return result.scalar_one_or_none()

    async def list_nodes(self) -> list[GraphNode]:
        """Return ALL nodes across all repos/branches (use sparingly)."""
        async with self._session() as sess:
            result = await sess.execute(select(GraphNode))
            return list(result.scalars().all())

    async def list_nodes_by_scope(
        self,
        *,
        repo_id: str,
        branch: str | None = None,
    ) -> list[GraphNode]:
        """Return nodes scoped to a specific repo_id, optionally filtered by branch."""
        async with self._session() as sess:
            stmt = select(GraphNode).where(GraphNode.repo_id == repo_id)
            if branch is not None:
                stmt = stmt.where(GraphNode.branch == branch)
            result = await sess.execute(stmt)
            return list(result.scalars().all())

    async def list_edges(self) -> list[GraphEdge]:
        """Return ALL edges across all repos (use sparingly)."""
        async with self._session() as sess:
            result = await sess.execute(select(GraphEdge))
            return list(result.scalars().all())

    async def list_edges_by_scope(self, *, repo_id: str) -> list[GraphEdge]:
        """Return edges scoped to a specific repo_id."""
        async with self._session() as sess:
            result = await sess.execute(
                select(GraphEdge).where(GraphEdge.repo_id == repo_id)
            )
            return list(result.scalars().all())

    async def query_by_type(self, node_type: str, *, repo_id: str = "") -> list[GraphNode]:
        async with self._session() as sess:
            stmt = select(GraphNode).where(GraphNode.node_type == node_type)
            if repo_id:
                stmt = stmt.where(GraphNode.repo_id == repo_id)
            result = await sess.execute(stmt)
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

    async def delete_nodes_by_scope(
        self,
        *,
        repo_id: str,
        branch: str | None = None,
        paths: set[str] | None = None,
    ) -> int:
        """Delete nodes for a given repo/branch scope.

        If *paths* is provided only nodes whose metadata.path matches are removed.
        Returns the number of nodes deleted.
        """
        nodes = await self.list_nodes_by_scope(repo_id=repo_id, branch=branch)
        deleted = 0
        for node in nodes:
            meta = dict(getattr(node, "node_metadata", {}) or {})
            if paths is not None:
                node_path = str(meta.get("path", "") or "")
                if node_path not in paths:
                    continue
            await self.delete_node(node.id)
            deleted += 1
        return deleted

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
    ) -> GraphEdge:
        """Insert a directed edge. Raises on duplicate (repo_id, source, target, relation)."""
        async with self._session() as sess:
            edge = GraphEdge(
                id=edge_id or uuid.uuid4(),
                repo_id=repo_id,
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
        *,
        repo_id: str = "",
    ) -> GraphEdge:
        """Insert or update edge by (repo_id, source, target, relation)."""
        async with self._session() as sess:
            result = await sess.execute(
                select(GraphEdge).where(
                    GraphEdge.repo_id == repo_id,
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
                repo_id=repo_id,
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
