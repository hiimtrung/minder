import inspect
from dataclasses import dataclass
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from minder.auth.middleware import AuthMiddleware
from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.models.user import User

ToolHandler = Callable[..., Any]


@dataclass(slots=True)
class RegisteredTool:
    name: str
    handler: ToolHandler
    require_auth: bool
    description: str | None = None


class BaseTransport:
    transport_name = "base"

    def __init__(self, *, config: MinderConfig, auth_service: AuthService | None = None) -> None:
        self._config = config
        self._middleware = AuthMiddleware(auth_service) if auth_service is not None else None
        self._server = FastMCP(
            name=config.server.name,
            host=config.server.host,
            port=config.server.port,
        )
        self._tools: dict[str, RegisteredTool] = {}

    @property
    def app(self) -> FastMCP:
        return self._server

    def register_tool(
        self,
        name: str,
        handler: ToolHandler,
        *,
        require_auth: bool = True,
        description: str | None = None,
    ) -> None:
        self._tools[name] = RegisteredTool(
            name=name,
            handler=handler,
            require_auth=require_auth,
            description=description,
        )

        async def wrapped_tool(**kwargs: Any) -> dict[str, Any] | list[Any] | str | int | float | bool | None:
            return await self.call_tool(
                name,
                arguments=kwargs,
                authorization=kwargs.pop("_authorization", None),
            )

        self._server.add_tool(
            wrapped_tool,
            name=name,
            description=description,
            structured_output=False,
        )

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    async def call_tool(
        self,
        name: str,
        *,
        arguments: dict[str, Any] | None = None,
        authorization: str | None = None,
    ) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")

        registered = self._tools[name]
        kwargs = dict(arguments or {})
        user = await self._authenticate_if_required(registered, authorization)
        if user is not None:
            kwargs["user"] = user
        return await _invoke(registered.handler, **kwargs)

    async def _authenticate_if_required(
        self,
        registered: RegisteredTool,
        authorization: str | None,
    ) -> User | None:
        if not registered.require_auth:
            return None
        if self._middleware is None:
            raise RuntimeError("Transport requires auth but no AuthService was configured")
        return await self._middleware.authenticate(authorization)


async def _invoke(handler: ToolHandler, **kwargs: Any) -> Any:
    result = handler(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result
