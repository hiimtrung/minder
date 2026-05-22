import uuid
from datetime import datetime, UTC
from typing import Any
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class GraphNodeSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    repo_id: str = ""
    branch: str = ""
    node_type: str
    name: str
    extra_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class GraphEdgeSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    repo_id: str = ""
    source_id: uuid.UUID
    target_id: uuid.UUID
    relation: str
    weight: float = 1.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
