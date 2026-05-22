import uuid
from datetime import datetime, UTC
from typing import Dict, Any, Optional
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class SessionSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: Optional[uuid.UUID] = None
    client_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    repo_id: Optional[uuid.UUID] = None
    project_context: Dict[str, Any] = Field(default_factory=dict)
    active_skills: Dict[str, Any] = Field(default_factory=dict)
    state: Dict[str, Any] = Field(default_factory=dict)
    ttl: int = 86400
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = Field(default_factory=lambda: datetime.now(UTC))
