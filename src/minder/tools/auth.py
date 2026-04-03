from __future__ import annotations

import uuid

from minder.auth.service import AuthService
from minder.store.relational import RelationalStore


class AuthTools:
    def __init__(self, store: RelationalStore, auth_service: AuthService) -> None:
        self._store = store
        self._auth = auth_service

    async def minder_auth_login(self, api_key: str) -> dict[str, str]:
        user = await self._auth.authenticate_api_key(api_key)
        return {"token": self._auth.issue_jwt(user), "user_id": str(user.id)}

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
