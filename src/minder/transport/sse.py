import json
import logging
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import BaseRoute
from minder.auth.context import set_current_principal
from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.presentation.http.admin.routes import dashboard_dev_origin
from minder.store.interfaces import ICacheProvider
from minder.transport.base import BaseTransport

logger = logging.getLogger(__name__)


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
            client_key = client_key_header.decode("utf-8") if client_key_header else None
             
            async def wrapped_receive() -> Any:
                message = await receive()
                if message["type"] == "http.request":
                    body = message.get("body", b"")
                    if body:
                        try:
                            # Attempt to inject _authorization into the JSON-RPC arguments
                            data = json.loads(body)
                            if isinstance(data, dict) and data.get("method") == "tools/call":
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
                            pass # Fallback to original body if parsing fails
                return message
             
            # Also set the context var just in case it can propagate
            try:
                if client_key:
                    principal = await self.auth_service.get_principal_from_client_key(client_key)
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
        auth_service: AuthService | None = None,
        extra_routes: list[BaseRoute] | None = None,
        cache_provider: ICacheProvider | None = None,
    ) -> None:
        super().__init__(config=config, auth_service=auth_service, cache_provider=cache_provider)
        self._extra_routes = list(extra_routes or [])

    async def run(self) -> None:
        """Custom run loop to handle starlette app with middleware."""
        # Get the Starlette app from FastMCP
        mcp_app = self._server.sse_app()

        app = Starlette(debug=True)
        dev_origin = dashboard_dev_origin(self._config)
        if dev_origin:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=[dev_origin],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        if self._middleware and self._middleware._auth:
            app.add_middleware(SSEAuthMiddleware, auth_service=self._middleware._auth)

        for route in self._extra_routes:
            app.router.routes.append(route)
        
        # Mount FastMCP app at root
        app.mount("/", mcp_app)
        
        config = uvicorn.Config(
            app, 
            host=self._config.server.host, 
            port=self._config.server.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()
