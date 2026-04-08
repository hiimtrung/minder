from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from minder.models.user import User


@dataclass(slots=True)
class Principal:
    principal_type: str
    principal_id: uuid.UUID
    role: str
    scopes: list[str] = field(default_factory=list)
    repo_scope: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AdminUserPrincipal(Principal):
    user: User | None = None

    def __init__(self, user: User) -> None:
        super().__init__(
            principal_type="user",
            principal_id=user.id,
            role=user.role,
            scopes=[],
            repo_scope=[],
            metadata={"email": user.email, "username": user.username},
        )
        self.user = user


@dataclass(slots=True)
class ClientPrincipal(Principal):
    client_id: uuid.UUID = field(init=False)
    client_slug: str = field(init=False)

    def __init__(
        self,
        *,
        client_id: uuid.UUID,
        client_slug: str,
        scopes: list[str],
        repo_scope: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            principal_type="client",
            principal_id=client_id,
            role="client",
            scopes=scopes,
            repo_scope=repo_scope,
            metadata=metadata or {},
        )
        self.client_id = client_id
        self.client_slug = client_slug
