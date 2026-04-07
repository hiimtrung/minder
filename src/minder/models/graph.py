"""
Knowledge Graph SQLAlchemy models.

GraphNode: any entity in the knowledge graph (module, file, service, owner).
GraphEdge: directed relationship between two nodes (depends_on, imports, calls, owns).
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
    node_type: str  # module | file | service | owner
    name: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GraphEdgeSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source_id: uuid.UUID
    target_id: uuid.UUID
    relation: str  # depends_on | owns | imports | calls
    weight: float = 1.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# SQLAlchemy ORM models
# ---------------------------------------------------------------------------


class GraphNode(Base):
    """A node in the knowledge graph — module, file, service, or owner."""

    __tablename__ = "graph_nodes"
    __table_args__ = (
        UniqueConstraint("node_type", "name", name="uq_graph_node_type_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    node_type: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    node_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GraphEdge(Base):
    """A directed edge between two graph nodes."""

    __tablename__ = "graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "target_id", "relation", name="uq_graph_edge_src_tgt_rel"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    relation: Mapped[str] = mapped_column(String, index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
