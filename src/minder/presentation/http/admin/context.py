from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from minder.application.admin.use_cases import AdminConsoleUseCases
from minder.auth.middleware import AuthMiddleware
from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.store.interfaces import ICacheProvider, IOperationalStore
from starlette.requests import Request

ADMIN_COOKIE_NAME = "minder_admin_token"


@dataclass(slots=True)
class AdminRouteContext:
    config: MinderConfig
    store: IOperationalStore
    cache: ICacheProvider | None
    auth_service: AuthService
    middleware: AuthMiddleware
    use_cases: AdminConsoleUseCases

    @classmethod
    def build(
        cls,
        *,
        config: MinderConfig,
        store: IOperationalStore,
        cache: ICacheProvider | None = None,
    ) -> "AdminRouteContext":
        auth_service = AuthService(store, config, cache=cache)
        middleware = AuthMiddleware(auth_service)
        use_cases = AdminConsoleUseCases(store=store, auth_service=auth_service, config=config)
        return cls(
            config=config,
            store=store,
            cache=cache,
            auth_service=auth_service,
            middleware=middleware,
            use_cases=use_cases,
        )

    def request_token(self, request: Request) -> str | None:
        authorization = request.headers.get("Authorization")
        if authorization:
            return authorization
        cookie_token = request.cookies.get(ADMIN_COOKIE_NAME)
        if cookie_token:
            return f"Bearer {cookie_token}"
        return None

    async def admin_user_from_request(self, request: Request) -> Any:
        user = await self.middleware.authenticate(self.request_token(request))
        if user.role != "admin":
            raise PermissionError("Admin role required")
        return user
