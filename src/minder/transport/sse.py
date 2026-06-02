import json
import logging
from contextlib import AsyncExitStack
from contextlib import asynccontextmanager
from typing import AsyncIterator
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute
from starlette.types import ASGIApp
from starlette.types import Receive
from starlette.types import Scope
from starlette.types import Send
from minder.auth.context import set_current_principal
from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.presentation.http.admin.routes import dashboard_dev_origin
from minder.observability.logging import (
    AccessLogMiddleware,
    CorrelationIdMiddleware,
    GlobalExceptionMiddleware,
)
from minder.store.interfaces import ICacheProvider, IOperationalStore
from minder.transport.base import BaseTransport

logger = logging.getLogger(__name__)


class MCPCompatApp:
    def __init__(self, *, sse_app: ASGIApp, streamable_http_app: ASGIApp) -> None:
        self._sse_app = sse_app
        self._streamable_http_app = streamable_http_app

    @staticmethod
    def _rewrite_path(scope: Scope, path: str) -> Scope:
        updated_scope = dict(scope)
        updated_scope["path"] = path
        updated_scope["raw_path"] = path.encode("utf-8")
        return updated_scope

    @staticmethod
    def _sse_guarded_send(send: Send) -> Send:
        """Return a send wrapper that prevents the inner SSE app's error middleware
        from sending a second ``http.response.start`` after streaming has begun.

        The inner Starlette SSE app includes its own ServerErrorMiddleware.  When
        the SSE client disconnects (or any exception occurs mid-stream), that
        middleware catches the exception and tries to send a 500 JSON error response
        — which requires a new ``http.response.start``.  But uvicorn has already
        locked the response to the first set of headers and raises:

            RuntimeError: Expected http.response.body, but got http.response.start

        This crashes the server process.  The guard below suppresses the duplicate
        ``http.response.start`` and converts the accompanying error body into a clean
        stream terminator (empty body, ``more_body=False``) so the connection closes
        gracefully instead of crashing.
        """
        headers_sent = False
        swallowing_error_response = False

        async def guarded(message: Any) -> None:
            nonlocal headers_sent, swallowing_error_response
            msg_type = message.get("type")

            if msg_type == "http.response.start":
                if headers_sent:
                    # Suppress duplicate start (error middleware trying to send 500).
                    swallowing_error_response = True
                    return
                headers_sent = True
                await send(message)

            elif msg_type == "http.response.body":
                if swallowing_error_response:
                    # Convert error body to an empty stream terminator so the
                    # SSE connection closes cleanly instead of sending garbled data.
                    swallowing_error_response = False
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                else:
                    await send(message)

            else:
                await send(message)

        return guarded

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._streamable_http_app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()

        if path == "/sse" and method in {"GET", "HEAD"}:
            await self._sse_app(scope, receive, self._sse_guarded_send(send))
            return

        if path.startswith("/messages"):
            await self._sse_app(scope, receive, self._sse_guarded_send(send))
            return

        if path == "/sse" and method in {"POST", "DELETE", "OPTIONS"}:
            await self._streamable_http_app(
                self._rewrite_path(scope, "/mcp"), receive, send
            )
            return

        await self._streamable_http_app(scope, receive, send)


class SSEAuthMiddleware:
    def __init__(self, app: Any, auth_service: AuthService) -> None:
        self.app = app
        self.auth_service = auth_service

    async def __call__(self, scope: Any, receive: Any, send: Any) -> Any:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization")
        client_key_header = headers.get(b"x-minder-client-key")

        # If we have an auth header and it's a POST,
        # we'll intercept the body to inject the authorization token as a hidden param.
        if (auth_header or client_key_header) and scope["method"] == "POST":
            auth_token = auth_header.decode("utf-8") if auth_header else None
            client_key = (
                client_key_header.decode("utf-8") if client_key_header else None
            )

            async def wrapped_receive() -> Any:
                message = await receive()
                if message["type"] == "http.request":
                    body = message.get("body", b"")
                    if body:
                        try:
                            # Attempt to inject _authorization into the JSON-RPC arguments
                            data = json.loads(body)
                            if (
                                isinstance(data, dict)
                                and data.get("method") == "tools/call"
                            ):
                                params = data.setdefault("params", {})
                                args = params.setdefault("arguments", {})
                                # Only inject if not already present
                                if auth_token and "minder_authorization" not in args:
                                    args["minder_authorization"] = auth_token
                                if client_key and "minder_client_key" not in args:
                                    args["minder_client_key"] = client_key
                                new_body = json.dumps(data).encode("utf-8")
                                message["body"] = new_body
                        except Exception:
                            pass  # Fallback to original body if parsing fails
                return message

            # Also set the context var just in case it can propagate
            try:
                if client_key:
                    principal = await self.auth_service.get_principal_from_client_key(
                        client_key
                    )
                else:
                    assert auth_token is not None
                    token = auth_token.strip()
                    if token.lower().startswith("bearer "):
                        token = token[7:].strip()
                    principal = await self.auth_service.get_principal_from_token(token)
                set_current_principal(principal)
            except Exception:
                pass

            return await self.app(scope, wrapped_receive, send)

        return await self.app(scope, receive, send)


class SSETransport(BaseTransport):
    transport_name = "sse"

    def __init__(
        self,
        *,
        config: MinderConfig,
        store: IOperationalStore | None = None,
        auth_service: AuthService | None = None,
        extra_routes: list[BaseRoute] | None = None,
        cache_provider: ICacheProvider,
    ) -> None:
        super().__init__(
            config=config,
            auth_service=auth_service,
            cache_provider=cache_provider,
            store=store,
        )
        self._extra_routes = list(extra_routes or [])
        self._legacy_sse_app: Starlette | None = None
        self._streamable_http_app: Starlette | None = None

    def extend_routes(self, routes: list[BaseRoute]) -> None:
        self._extra_routes.extend(routes)

    @staticmethod
    async def _oauth_protected_resource_metadata(request: Request) -> JSONResponse:
        base_url = str(request.base_url).rstrip("/")
        return JSONResponse(
            {
                "resource": f"{base_url}/mcp",
                "authorization_servers": [],
            }
        )

    @asynccontextmanager
    async def _app_lifespan(self, app: Starlette) -> AsyncIterator[None]:
        del app
        async with AsyncExitStack() as stack:
            if self._legacy_sse_app is not None:
                await stack.enter_async_context(
                    self._legacy_sse_app.router.lifespan_context(self._legacy_sse_app)
                )
            if self._streamable_http_app is not None:
                await stack.enter_async_context(
                    self._streamable_http_app.router.lifespan_context(
                        self._streamable_http_app
                    )
                )
            yield

    def build_starlette_app(self) -> Starlette:
        legacy_sse_app: Starlette = self._server.sse_app()
        streamable_http_app: Starlette = self._server.streamable_http_app()
        self._legacy_sse_app = legacy_sse_app
        self._streamable_http_app = streamable_http_app
        mcp_app = MCPCompatApp(
            sse_app=legacy_sse_app,
            streamable_http_app=streamable_http_app,
        )

        app = Starlette(lifespan=self._app_lifespan)
        app.state.store = self._store
        app.state.config = self._config
        dev_origin = dashboard_dev_origin(self._config)
        if dev_origin:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=[dev_origin],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        # Observability middleware
        app.add_middleware(GlobalExceptionMiddleware)
        app.add_middleware(CorrelationIdMiddleware)
        app.add_middleware(AccessLogMiddleware)

        if self._middleware and self._middleware._auth:
            app.add_middleware(SSEAuthMiddleware, auth_service=self._middleware._auth)

        for route in self._extra_routes:
            app.router.routes.append(route)

        app.add_route(
            "/.well-known/oauth-protected-resource",
            self._oauth_protected_resource_metadata,
            methods=["GET"],
        )
        app.add_route(
            "/.well-known/oauth-protected-resource/sse",
            self._oauth_protected_resource_metadata,
            methods=["GET"],
        )
        app.add_route(
            "/.well-known/oauth-protected-resource/mcp",
            self._oauth_protected_resource_metadata,
            methods=["GET"],
        )

        app.mount("/", mcp_app)
        return app

    async def run(self) -> None:
        """Custom run loop to handle starlette app with middleware."""
        app = self.build_starlette_app()

        config = uvicorn.Config(
            app,
            host=self._config.server.host,
            port=self._config.server.port,
            log_level="info",
            # Keep-alive timeout — frees idle connections faster so the server
            # can accept new ones during long-running LLM requests.
            timeout_keep_alive=self._config.server.http_timeout_keep_alive,
            # Allow multiple concurrent request handler coroutines.
            # loop="auto" lets uvicorn pick the best async loop implementation.
            loop="auto",
        )
        server = uvicorn.Server(config)
        await server.serve()
