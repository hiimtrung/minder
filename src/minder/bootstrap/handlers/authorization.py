"""
Authorization Helpers — extracted from bootstrap/transport.py.

These utility functions enforce authorization rules (repo access, admin check)
and are shared across all handler modules. They depend only on domain types
(Principal, AuthError) and are infrastructure-agnostic.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from minder.auth.principal import ClientPrincipal, Principal
from minder.domain.exceptions import AuthError
from minder.domain.interfaces.repositories import IOperationalStore


def require_authenticated_user(user: Any | None) -> Any:
    """Raise AuthError if no authenticated user is present."""
    if user is None:
        raise AuthError("AUTH_FORBIDDEN", "Authenticated user required")
    return user


def require_admin_user(user: Any | None) -> Any:
    """Raise AuthError if user is not authenticated or not an admin."""
    authenticated_user = require_authenticated_user(user)
    if getattr(authenticated_user, "role", None) != "admin":
        raise AuthError("AUTH_FORBIDDEN", "Admin role required")
    return authenticated_user


def ensure_client_repo_access(
    principal: Principal | None,
    *,
    repo_path: str,
) -> None:
    """Raise AuthError if a ClientPrincipal lacks access to the given repo."""
    if not isinstance(principal, ClientPrincipal):
        return
    scopes = [
        scope.strip().rstrip("/")
        for scope in principal.repo_scope
        if scope and scope.strip()
    ]
    repo_root = Path(repo_path).resolve()
    candidates = {repo_path.rstrip("/"), str(repo_root).rstrip("/"), repo_root.name}
    if not scopes or (
        "*" not in scopes
        and not any(
            any(
                candidate == scope or candidate.startswith(f"{scope}/")
                for candidate in candidates
            )
            for scope in scopes
        )
    ):
        raise AuthError(
            "AUTH_FORBIDDEN", "Client is not allowed to inspect this repository"
        )


async def resolve_repo_uuid(
    repo_id: str,
    store: IOperationalStore,
) -> uuid.UUID:
    """Accept a UUID string or a repo name/slug; return the UUID."""
    try:
        return uuid.UUID(repo_id)
    except ValueError:
        pass
    repo = await store.get_repository_by_name(repo_id)
    if repo is None:
        raise ValueError(f"Repository not found: {repo_id!r}")
    return repo.id


def extract_owner_id(
    *,
    principal: Principal | None = None,
    user: Any | None = None,
) -> uuid.UUID | None:
    """Extract the owner ID from a principal or user for multi-tenant isolation."""
    if principal is not None:
        return principal.principal_id
    if user is not None:
        return user.id
    return None
