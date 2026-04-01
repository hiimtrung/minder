from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class GraphState(BaseModel):
    query: str
    session_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    repo_id: uuid.UUID | None = None
    repo_path: str | None = None
    plan: dict[str, Any] = Field(default_factory=dict)
    retrieved_docs: list[dict[str, Any]] = Field(default_factory=list)
    reranked_docs: list[dict[str, Any]] = Field(default_factory=list)
    workflow_context: dict[str, Any] = Field(default_factory=dict)
    reasoning_output: dict[str, Any] = Field(default_factory=dict)
    llm_output: dict[str, Any] = Field(default_factory=dict)
    guard_result: dict[str, Any] = Field(default_factory=dict)
    verification_result: dict[str, Any] = Field(default_factory=dict)
    evaluation: dict[str, Any] = Field(default_factory=dict)
    transition_log: list[dict[str, Any]] = Field(default_factory=list)
    retry_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
