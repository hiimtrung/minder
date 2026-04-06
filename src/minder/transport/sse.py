import json
import logging
from typing import Any

import uvicorn
from starlette.applications import Starlette
from minder.auth.context import set_current_user
from minder.auth.service import AuthError, AuthService
from minder.config import MinderConfig
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
        
        # If we have an auth header and it's a POST, 
        # we'll intercept the body to inject the authorization token as a hidden param.
        if auth_header and scope["method"] == "POST":
            auth_token = auth_header.decode("utf-8")
             
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
                                if "_authorization" not in args:
                                    args["_authorization"] = auth_token
                                    new_body = json.dumps(data).encode("utf-8")
                                    message["body"] = new_body
                        except Exception:
                            pass # Fallback to original body if parsing fails
                return message
             
            # Also set the context var just in case it can propagate
            try:
                token = auth_token.strip()
                if token.lower().startswith("bearer "):
                    token = token[7:].strip()
                user = await self.auth_service.get_user_from_jwt(token)
                set_current_user(user)
            except Exception:
                pass

            return await self.app(scope, wrapped_receive, send)

        return await self.app(scope, receive, send)


class SSETransport(BaseTransport):
    transport_name = "sse"

    def __init__(self, *, config: MinderConfig, auth_service: AuthService | None = None) -> None:
        super().__init__(config=config, auth_service=auth_service)

    async def run(self) -> None:
        """Custom run loop to handle starlette app with middleware."""
        # Get the Starlette app from FastMCP
        mcp_app = self._server.sse_app()

        app = Starlette(debug=True)
        if self._middleware and self._middleware._auth:
            app.add_middleware(SSEAuthMiddleware, auth_service=self._middleware._auth)
        
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
