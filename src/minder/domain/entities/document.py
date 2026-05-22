import uuid
from datetime import datetime, UTC
from typing import Dict, Any, List, Optional
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class DocumentSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    content: str
    doc_type: str
    source_path: str
    chunks: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None
    project: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
