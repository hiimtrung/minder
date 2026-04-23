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
        node_types: set[str] | None = None,
    ) -> list[GraphNode]:
        """Fetch nodes scoped to a repository and optionally a branch."""
        async with self._session() as sess:
            stmt = select(GraphNode).where(GraphNode.repo_id == repo_id)
            if branch is not None:
                stmt = stmt.where(GraphNode.branch == branch)
            if node_types:
                stmt = stmt.where(GraphNode.node_type.in_(list(node_types)))
            
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
        """Delete nodes for a given repo/branch scope efficiently."""
        async with self._session() as sess:
            # 1. Build the base statement
            stmt = select(GraphNode).where(GraphNode.repo_id == repo_id)
            if branch is not None:
                stmt = stmt.where(GraphNode.branch == branch)
            
            # If we are deleting by paths, we must fetch and filter
            if paths is not None:
                result = await sess.execute(stmt)
                to_delete_ids: set[uuid.UUID] = set()
                for node in result.scalars().all():
                    meta = dict(node.node_metadata or {})
                    if str(meta.get("path", "") or "") in paths:
                        to_delete_ids.add(node.id)
                
                if not to_delete_ids:
                    return 0

                # Delete edges incident to these nodes
                edge_stmt = delete(GraphEdge).where(
                    (GraphEdge.source_id.in_(list(to_delete_ids))) | 
                    (GraphEdge.target_id.in_(list(to_delete_ids)))
                )
                await sess.execute(edge_stmt)

                # Delete the nodes
                node_del_stmt = delete(GraphNode).where(GraphNode.id.in_(list(to_delete_ids)))
                del_result = await sess.execute(node_del_stmt)
                return int(del_result.rowcount)  # type: ignore
            else:
                # Optimized branch-wide deletion (no path filter)
                # First delete edges
                edge_stmt = delete(GraphEdge).where(GraphEdge.repo_id == repo_id)
                # Note: if branch is specified, we can't easily delete edges by branch 
                # unless we join with graph_nodes, or we add branch to graph_edges column.
                # Since graph_edges v2 has repo_id but NOT branch, we'll fetch IDs if branch is specified.
                if branch is not None:
                    result = await sess.execute(select(GraphNode.id).where(GraphNode.repo_id == repo_id, GraphNode.branch == branch))
                    node_ids = [r for r in result.scalars().all()]
                    if not node_ids:
                        return 0
                    await sess.execute(delete(GraphEdge).where((GraphEdge.source_id.in_(node_ids)) | (GraphEdge.target_id.in_(node_ids))))
                    del_result = await sess.execute(delete(GraphNode).where(GraphNode.id.in_(node_ids)))
                else:
                    await sess.execute(edge_stmt)
                    del_result = await sess.execute(delete(GraphNode).where(GraphNode.repo_id == repo_id))
                
                return int(del_result.rowcount)  # type: ignore

    async def list_repo_branches(self, repo_id: str) -> list[str]:
        """Return unique branches that have nodes for this repository."""
        async with self._session() as sess:
            stmt = select(GraphNode.branch).where(GraphNode.repo_id == repo_id).distinct()
            result = await sess.execute(stmt)
            return [str(b) for b in result.scalars().all() if b]

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

    async def bulk_upsert_nodes(
        self,
        nodes: list[dict[str, Any]],
        *,
        repo_id: str,
        branch: str = "",
    ) -> dict[tuple[str, str], uuid.UUID]:
        """Upsert many nodes in a single transaction.
        
        Returns a mapping of (node_type, name) -> id.
        """
        async with self._session() as sess:
            # 1. Fetch existing nodes to handle merging if needed
            # For simplicity and performance, we'll fetch all nodes for this repo/branch
            stmt = select(GraphNode).where(
                GraphNode.repo_id == repo_id,
                GraphNode.branch == branch
            )
            result = await sess.execute(stmt)
            existing_map = {
                (n.node_type, n.name): n for n in result.scalars().all()
            }
            
            id_map: dict[tuple[str, str], uuid.UUID] = {}
            
            for node_data in nodes:
                node_type = node_data["node_type"]
                name = node_data["name"]
                metadata = node_data.get("metadata") or {}
                key = (node_type, name)
                
                if key in existing_map:
                    existing = existing_map[key]
                    if metadata:
                        # Merge metadata
                        existing.node_metadata = {**dict(existing.node_metadata), **metadata}
                    id_map[key] = existing.id
                else:
                    new_node = GraphNode(
                        id=uuid.uuid4(),
                        repo_id=repo_id,
                        branch=branch,
                        node_type=node_type,
                        name=name,
                        node_metadata=metadata,
                    )
                    sess.add(new_node)
                    id_map[key] = new_node.id
            
            await sess.flush()
            return id_map

    async def bulk_upsert_edges(
        self,
        edges: list[dict[str, Any]],
        *,
        repo_id: str,
    ) -> int:
        """Upsert many edges in a single transaction."""
        async with self._session() as sess:
            # Edges are tricky because they link by UUID.
            # We assume source_id and target_id are already resolved.
            
            # Fetch existing edges for this repo to avoid duplicates
            stmt = select(GraphEdge).where(GraphEdge.repo_id == repo_id)
            result = await sess.execute(stmt)
            existing_edges = {
                (e.source_id, e.target_id, e.relation): e for e in result.scalars().all()
            }
            
            upserted = 0
            for edge_data in edges:
                source_id = edge_data["source_id"]
                target_id = edge_data["target_id"]
                relation = edge_data["relation"]
                weight = edge_data.get("weight", 1.0)
                key = (source_id, target_id, relation)
                
                if key in existing_edges:
                    existing = existing_edges[key]
                    existing.weight = weight
                else:
                    new_edge = GraphEdge(
                        id=uuid.uuid4(),
                        repo_id=repo_id,
                        source_id=source_id,
                        target_id=target_id,
                        relation=relation,
                        weight=weight,
                    )
                    sess.add(new_edge)
                upserted += 1
            
            return upserted

    async def search_nodes(
        self,
        query: str,
        *,
        repo_id: str | None = None,
        branch: str | None = None,
        node_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[GraphNode]:
        """Search nodes by name or metadata using database-level filtering."""
        async with self._session() as sess:
            # Simple LIKE search on name
            stmt = select(GraphNode).where(GraphNode.name.ilike(f"%{query}%"))
            
            if repo_id:
                stmt = stmt.where(GraphNode.repo_id == repo_id)
            if branch:
                stmt = stmt.where(GraphNode.branch == branch)
            if node_types:
                stmt = stmt.where(GraphNode.node_type.in_(node_types))
                
            stmt = stmt.limit(limit)
            result = await sess.execute(stmt)
            return list(result.scalars().all())

    async def list_repositories(self) -> list[Any]:
        # This is just a placeholder if needed, usually handled by IRepositoryRepo
        return []

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

    async def get_neighborhood(
        self,
        node_id: uuid.UUID,
        *,
        max_depth: int = 4,
        max_nodes: int = 100,
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        """
        Return nodes and edges in the neighborhood of a seed node using BFS.
        """
        async with self._session() as sess:
            nodes_map: dict[uuid.UUID, GraphNode] = {}
            edges_map: dict[uuid.UUID, GraphEdge] = {}
            
            current_level_ids: set[uuid.UUID] = {node_id}
            visited_ids: set[uuid.UUID] = set()
            
            for depth in range(max_depth + 1):
                if not current_level_ids or len(nodes_map) >= max_nodes:
                    break
                
                # Fetch nodes for current level
                node_ids_to_fetch = [nid for nid in current_level_ids if nid not in nodes_map]
                if node_ids_to_fetch:
                    n_res = await sess.execute(
                        select(GraphNode).where(GraphNode.id.in_(node_ids_to_fetch))
                    )
                    for node in n_res.scalars().all():
                        if len(nodes_map) < max_nodes:
                            nodes_map[node.id] = node
                
                if depth < max_depth:
                    # Fetch edges incident to current level nodes
                    e_res = await sess.execute(
                        select(GraphEdge).where(
                            (GraphEdge.source_id.in_(list(current_level_ids))) | 
                            (GraphEdge.target_id.in_(list(current_level_ids)))
                        )
                    )
                    next_level_ids: set[uuid.UUID] = set()
                    for edge in e_res.scalars().all():
                        edges_map[edge.id] = edge
                        next_level_ids.add(edge.source_id)
                        next_level_ids.add(edge.target_id)
                    
                    visited_ids.update(current_level_ids)
                    current_level_ids = next_level_ids - visited_ids
            
            # Ensure edges only connect nodes we actually kept
            final_node_ids = set(nodes_map.keys())
            final_edges = [
                e for e in edges_map.values() 
                if e.source_id in final_node_ids and e.target_id in final_node_ids
            ]
            
            return list(nodes_map.values()), final_edges
