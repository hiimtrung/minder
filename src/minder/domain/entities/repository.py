import uuid
from datetime import datetime, UTC
from typing import Dict, Any, List, Optional
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class RepositorySchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    repo_name: str
    repo_url: str
    default_branch: str
    tracked_branches: List[str] = Field(default_factory=list)
    workflow_id: Optional[uuid.UUID] = None
    state_path: str = ".minder"
    context_snapshot: Dict[str, Any] = Field(default_factory=dict)
    relationships: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class RepositoryWorkflowStateSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    repo_id: uuid.UUID
    branch: str = "main"
    session_id: Optional[uuid.UUID] = None
    current_step: str
    completed_steps: List[str] = Field(default_factory=list)
    blocked_by: List[str] = Field(default_factory=list)
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    next_step: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
