from __future__ import annotations

import uuid
from typing import Any

from minder.application.admin.dto import (
    ActivityEventPayload,
    AdminLoginPayload,
    AdminSessionPayload,
    AuditEventPayload,
    AuditListPayload,
    ClientConnectionTestPayload,
    ClientDetailPayload,
    ClientKeyPayload,
    ClientListPayload,
    ClientPayload,
    CreateClientPayload,
    OnboardingPayload,
    RevokeKeysPayload,
    SetupResultPayload,
)
from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.store.interfaces import IOperationalStore

DASHBOARD_TOOL_SCOPE_OPTIONS = [
    "minder_query",
    "minder_search_code",
    "minder_search_errors",
    "minder_search",
    "minder_memory_recall",
    "minder_workflow_get",
    "minder_workflow_step",
]

DASHBOARD_TOOL_SCOPE_PRESETS: dict[str, list[str]] = {
    "Query Only": ["minder_query", "minder_search_code", "minder_search_errors"],
    "Read Only": [
        "minder_query",
        "minder_search_code",
        "minder_search_errors",
        "minder_search",
        "minder_memory_recall",
        "minder_workflow_get",
    ],
    "Full Dev Assistant": DASHBOARD_TOOL_SCOPE_OPTIONS,
}


class AdminConsoleUseCases:
    def __init__(
        self,
        *,
        store: IOperationalStore,
        auth_service: AuthService,
        config: MinderConfig,
    ) -> None:
        self._store = store
        self._auth_service = auth_service
        self._config = config

    async def has_admin_users(self) -> bool:
        return await self._auth_service.has_admin_users()

    async def create_initial_admin(
        self,
        *,
        username: str,
        email: str,
        display_name: str,
    ) -> SetupResultPayload:
        _user, api_key = await self._auth_service.register_user(
            email=email,
            username=username,
            display_name=display_name,
            role="admin",
        )
        return {"api_key": api_key}

    async def login_admin(self, api_key: str) -> AdminLoginPayload:
        user = await self._auth_service.authenticate_api_key(api_key)
        if user.role != "admin":
            raise PermissionError("Admin role required")
        return {"jwt": self._auth_service.issue_jwt(user)}

    @staticmethod
    def serialize_admin_session(user: Any) -> AdminSessionPayload:
        return {
            "id": str(user.id),
            "username": str(user.username),
            "email": str(user.email),
            "display_name": str(user.display_name),
            "role": str(user.role),
        }

    async def exchange_client_key(
        self,
        *,
        client_api_key: str,
        requested_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._auth_service.exchange_client_api_key(
            client_api_key,
            requested_scopes=requested_scopes,
        )

    async def list_clients(self) -> ClientListPayload:
        return {"clients": [self.serialize_client(client) for client in await self._store.list_clients()]}

    async def create_client(
        self,
        *,
        actor_user_id: uuid.UUID,
        name: str,
        slug: str,
        description: str = "",
        tool_scopes: list[str] | None = None,
        repo_scopes: list[str] | None = None,
    ) -> CreateClientPayload:
        client, client_api_key = await self._auth_service.register_client(
            name=name,
            slug=slug,
            description=description,
            created_by_user_id=actor_user_id,
            tool_scopes=tool_scopes,
            repo_scopes=repo_scopes,
        )
        return {
            "client": self.serialize_client(client),
            "client_api_key": client_api_key,
        }

    async def get_client_detail(self, client_id: uuid.UUID) -> ClientDetailPayload:
        client = await self._store.get_client_by_id(client_id)
        if client is None:
            raise LookupError("Client not found")
        return {"client": self.serialize_client(client)}

    async def update_client(
        self,
        *,
        client_id: uuid.UUID,
        description: str,
        repo_scopes: list[str],
        tool_scopes: list[str],
    ) -> ClientDetailPayload:
        updated = await self._store.update_client(
            client_id,
            description=description,
            repo_scopes=repo_scopes,
            tool_scopes=tool_scopes,
        )
        if updated is None:
            raise LookupError("Client not found")
        return {"client": self.serialize_client(updated)}

    async def issue_client_key(
        self,
        *,
        client_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> ClientKeyPayload:
        client_api_key = await self._auth_service.create_client_api_key(
            client_id=client_id,
            created_by_user_id=actor_user_id,
        )
        return {"client_api_key": client_api_key}

    async def revoke_client_keys(
        self,
        *,
        client_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> RevokeKeysPayload:
        await self._auth_service.revoke_client_api_keys(client_id, actor_user_id=actor_user_id)
        return {"revoked": True}

    async def get_onboarding(self, client_id: uuid.UUID) -> OnboardingPayload:
        client = await self._store.get_client_by_id(client_id)
        if client is None:
            raise LookupError("Client not found")
        return {
            "client": self.serialize_client(client),
            "templates": self.onboarding_templates(client),
        }

    async def test_client_connection(self, client_api_key: str) -> ClientConnectionTestPayload:
        client = await self._auth_service.authenticate_client_api_key(client_api_key)
        return {
            "ok": True,
            "client": self.serialize_client(client),
            "templates": self.onboarding_templates(client),
        }

    async def list_audit(self, *, actor_id: str | None = None) -> AuditListPayload:
        events = await self._store.list_audit_logs(actor_id=actor_id)
        return {"events": [self.serialize_audit_event(event) for event in events]}

    async def get_recent_client_activity(
        self,
        client_id: uuid.UUID,
        *,
        limit: int = 8,
    ) -> list[ActivityEventPayload]:
        events = await self._store.list_audit_logs()
        filtered = [event for event in events if str(getattr(event, "resource_id", "")) == str(client_id)]
        filtered.sort(key=lambda event: getattr(event, "created_at", None) or "", reverse=True)
        return [
            {
                "event_type": str(getattr(event, "event_type", "")),
                "created_at": getattr(event, "created_at").isoformat() if getattr(event, "created_at", None) else "unknown time",
            }
            for event in filtered[:limit]
        ]

    async def list_repo_scope_candidates(self) -> list[str]:
        candidates = ["*", "/workspace/repo", "/workspace/docs"]
        clients = await self._store.list_clients()
        for client in clients:
            candidates.extend(list(getattr(client, "repo_scopes", [])))
        return self.dedupe_preserve_order(candidates)

    def onboarding_templates(self, client: Any) -> dict[str, str]:
        exchange_url = "/v1/auth/token-exchange"
        query_hint = client.tool_scopes[0] if client.tool_scopes else "minder_query"
        base_url = f"http://localhost:{self._config.server.port}"
        return {
            "codex": (
                f'{{"server_url":"{base_url}/sse","client_api_key":"<mkc_...>",'
                f'"bootstrap_path":"{exchange_url}","client_slug":"{client.slug}","preferred_tool":"{query_hint}"}}'
            ),
            "copilot": (
                f'{{"type":"mcp","url":"{base_url}/sse","headers":{{"X-Minder-Client-Key":"<mkc_...>"}},"client":"{client.slug}"}}'
            ),
            "claude_desktop": (
                f'{{"mcpServers":{{"minder":{{"url":"{base_url}/sse","headers":{{"X-Minder-Client-Key":"<mkc_...>"}},"client":"{client.slug}"}}}}}}'
            ),
        }

    @staticmethod
    def split_csv(raw: str) -> list[str]:
        return [item.strip() for item in raw.split(",") if item.strip()]

    @staticmethod
    def dedupe_preserve_order(values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                deduped.append(value)
        return deduped

    @staticmethod
    def serialize_client(client: Any) -> ClientPayload:
        return {
            "id": str(client.id),
            "name": client.name,
            "slug": client.slug,
            "description": getattr(client, "description", ""),
            "status": client.status,
            "tool_scopes": list(client.tool_scopes),
            "repo_scopes": list(client.repo_scopes),
            "workflow_scopes": list(getattr(client, "workflow_scopes", [])),
            "transport_modes": list(getattr(client, "transport_modes", [])),
        }

    @staticmethod
    def serialize_audit_event(event: Any) -> AuditEventPayload:
        return {
            "id": str(event.id),
            "actor_type": event.actor_type,
            "actor_id": event.actor_id,
            "event_type": event.event_type,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "outcome": event.outcome,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
