from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from minder.application.admin.use_cases import AdminConsoleUseCases
from minder.auth.principal import ClientPrincipal, Principal
from minder.auth.middleware import AuthMiddleware
from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.store.interfaces import ICacheProvider, IGraphRepository, IOperationalStore
from starlette.requests import Request

ADMIN_COOKIE_NAME = "minder_admin_token"


@dataclass(slots=True)
class AdminRouteContext:
    config: MinderConfig
    store: IOperationalStore
    graph_store: IGraphRepository | None
    cache: ICacheProvider | None
    auth_service: AuthService
    middleware: AuthMiddleware
    use_cases: AdminConsoleUseCases
    prompt_sync_hook: Callable[[], Awaitable[None]] | None = None

    @classmethod
    def build(
        cls,
        *,
        config: MinderConfig,
        store: IOperationalStore,
        graph_store: IGraphRepository | None = None,
        cache: ICacheProvider | None = None,
        prompt_sync_hook: Callable[[], Awaitable[None]] | None = None,
    ) -> "AdminRouteContext":
        auth_service = AuthService(store, config, cache=cache)
        middleware = AuthMiddleware(auth_service)
        use_cases = AdminConsoleUseCases(
            store=store,
            auth_service=auth_service,
            config=config,
            graph_store=graph_store,
        )
        return cls(
            config=config,
            store=store,
            graph_store=graph_store,
            cache=cache,
            auth_service=auth_service,
            middleware=middleware,
            use_cases=use_cases,
            prompt_sync_hook=prompt_sync_hook,
        )

    def request_token(self, request: Request) -> str | None:
        authorization = request.headers.get("Authorization")
        if authorization:
            return authorization
        cookie_token = request.cookies.get(ADMIN_COOKIE_NAME)
        if cookie_token:
            return f"Bearer {cookie_token}"
        return None

    @staticmethod
    def request_client_key(request: Request) -> str | None:
        client_key = request.headers.get("X-Minder-Client-Key")
        if client_key and client_key.strip():
            return client_key.strip()
        return None

    async def principal_from_request(
        self,
        request: Request,
        *,
        requested_scopes: list[str] | None = None,
    ) -> Principal:
        return await self.middleware.authenticate_principal(
            self.request_token(request),
            client_key=self.request_client_key(request),
        )

    async def client_principal_from_request(self, request: Request) -> ClientPrincipal:
        principal = await self.principal_from_request(request)
        if not isinstance(principal, ClientPrincipal):
            raise PermissionError("Client principal required")
        return principal

    async def admin_user_from_request(self, request: Request) -> Any:
        user = await self.middleware.authenticate(self.request_token(request))
        if user.role != "admin":
            raise PermissionError("Admin role required")
        return user
