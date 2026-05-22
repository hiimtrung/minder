import uuid
from datetime import datetime, UTC
from typing import Dict, Any, List, Optional
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class SkillSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    content: str
    language: str
    tags: List[str] = Field(default_factory=list)
    embedding: Optional[List[float]] = None
    usage_count: int = 0
    quality_score: float = 0.0
    deprecated: bool = False
    source_metadata: Optional[Dict[str, Any]] = None
    excerpt_kind: str = "none"
    owner_id: Optional[uuid.UUID] = None
    scope: str = "private"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
