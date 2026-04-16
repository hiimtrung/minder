"""
Knowledge Graph SQLAlchemy models.

GraphNode: any entity in the knowledge graph (module, file, service, owner).
GraphEdge: directed relationship between two nodes (depends_on, imports, calls, owns).

v2 schema adds repo_id + branch columns so nodes from different repositories
and branches are stored independently.  UniqueConstraint is now
(repo_id, branch, node_type, name).

Migration from v1 is handled by KnowledgeGraphStore.init_db() which calls
_migrate_graph_v2() on first boot when the columns are absent.
"""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from typing import Any

from pydantic import Field
from sqlalchemy import DateTime, Float, JSON, String, UUID, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BaseModelMeta


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class GraphNodeSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    repo_id: str = ""
    branch: str = ""
    node_type: str  # module | file | service | owner | route | api_endpoint | websocket_endpoint | mq_topic | …
    name: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GraphEdgeSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    repo_id: str = ""
    source_id: uuid.UUID
    target_id: uuid.UUID
    relation: str  # depends_on | owns | imports | calls | exposes_route | publishes | consumes | cross_repo_calls
    weight: float = 1.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# SQLAlchemy ORM models
# ---------------------------------------------------------------------------


class GraphNode(Base):
    """A node in the knowledge graph — module, file, service, or owner.

    v2: scoped by (repo_id, branch) so nodes from different repositories or
    branches never collide.  repo_id="" and branch="" denotes global/shared
    nodes (e.g. external packages used by many repos).
    """

    __tablename__ = "graph_nodes"
    __table_args__ = (
        # v2 constraint: repo_id + branch + type + name must be unique
        UniqueConstraint(
            "repo_id", "branch", "node_type", "name",
            name="uq_graph_node_repo_branch_type_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Scope columns (v2) — empty string = "global / no specific repo"
    repo_id: Mapped[str] = mapped_column(String, index=True, default="", server_default="")
    branch: Mapped[str] = mapped_column(String, index=True, default="", server_default="")
    node_type: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    node_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GraphEdge(Base):
    """A directed edge between two graph nodes.

    v2: repo_id added for efficient repo-scoped edge queries.
    """

    __tablename__ = "graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "repo_id", "source_id", "target_id", "relation",
            name="uq_graph_edge_repo_src_tgt_rel",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Scope column (v2)
    repo_id: Mapped[str] = mapped_column(String, index=True, default="", server_default="")
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    relation: Mapped[str] = mapped_column(String, index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
