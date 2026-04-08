from __future__ import annotations

import uuid

from minder.auth.service import AuthService
from minder.store.interfaces import IOperationalStore


class AuthTools:
    def __init__(self, store: IOperationalStore, auth_service: AuthService) -> None:
        self._store = store
        self._auth = auth_service

    async def minder_auth_login(self, api_key: str) -> dict[str, str]:
        user = await self._auth.authenticate_api_key(api_key)
        return {"token": self._auth.issue_jwt(user), "user_id": str(user.id)}

    async def minder_auth_exchange_client_key(
        self,
        client_api_key: str,
        *,
        requested_scopes: list[str] | None = None,
    ) -> dict[str, object]:
        return await self._auth.exchange_client_api_key(
            client_api_key,
            requested_scopes=requested_scopes,
        )

    async def minder_auth_whoami(self, token: str) -> dict[str, str]:
        user = await self._auth.get_user_from_jwt(token)
        return {
            "user_id": str(user.id),
            "email": user.email,
            "username": user.username,
            "role": user.role,
        }

    async def minder_auth_manage(
        self,
        *,
        actor_user_id: uuid.UUID,
        action: str,
    ) -> dict[str, object]:
        actor = await self._store.get_user_by_id(actor_user_id)
        if actor is None or actor.role != "admin":
            raise PermissionError("Admin role required")
        if action == "list_users":
            users = await self._store.list_users(active_only=False)
            return {
                "users": [
                    {
                        "id": str(user.id),
                        "email": user.email,
                        "username": user.username,
                        "role": user.role,
                        "is_active": user.is_active,
                    }
                    for user in users
                ]
            }
        raise ValueError(f"Unsupported auth manage action: {action}")

    async def minder_auth_create_client(
        self,
        *,
        actor_user_id: uuid.UUID,
        name: str,
        slug: str,
        description: str = "",
        tool_scopes: list[str] | None = None,
        repo_scopes: list[str] | None = None,
    ) -> dict[str, object]:
        actor = await self._store.get_user_by_id(actor_user_id)
        if actor is None or actor.role != "admin":
            raise PermissionError("Admin role required")
        client, client_api_key = await self._auth.register_client(
            name=name,
            slug=slug,
            description=description,
            created_by_user_id=actor_user_id,
            tool_scopes=tool_scopes,
            repo_scopes=repo_scopes,
        )
        return {
            "client": {
                "id": str(client.id),
                "name": client.name,
                "slug": client.slug,
                "status": client.status,
                "tool_scopes": list(client.tool_scopes),
                "repo_scopes": list(client.repo_scopes),
            },
            "client_api_key": client_api_key,
        }
