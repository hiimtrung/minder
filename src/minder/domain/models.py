from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


@dataclass(frozen=True)
class Workspace:
    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class Repository:
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    repo_url: str
    default_branch: str = "main"
    local_path: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class Contract:
    id: uuid.UUID
    workspace_id: uuid.UUID
    repo_id: uuid.UUID
    kind: Literal["http_route", "dto_schema", "grpc_method", "event_schema", "db_model"]
    identifier: str
    raw_definition: str
    source_file: str
    start_line: int
    end_line: int
    language: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CodeChunk:
    id: uuid.UUID
    workspace_id: uuid.UUID
    repo_id: uuid.UUID
    file_path: str
    symbol_name: str | None
    language: str
    start_line: int
    end_line: int
    content: str
    imports_context: str = ""
    embedding: list[float] | None = None


@dataclass(frozen=True)
class Memory:
    id: uuid.UUID
    workspace_id: uuid.UUID | None
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    quality_score: float = 0.0
    usage_count: int = 0
    embedding: list[float] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class Skill:
    id: uuid.UUID
    title: str
    content: str
    language: str
    tags: list[str] = field(default_factory=list)
    quality_score: float = 0.0
    usage_count: int = 0
    deprecated: bool = False
    embedding: list[float] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class SessionState:
    id: uuid.UUID
    user_id: str
    workspace_id: uuid.UUID | None
    name: str
    state: dict[str, Any] = field(default_factory=dict)
    active_files: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
