import logging
import inspect
from dataclasses import dataclass
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from minder.auth.middleware import AuthMiddleware
from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.models.user import User
from minder.auth.context import get_current_user

logger = logging.getLogger(__name__)

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

        # We need to wrap the handler to inject auth logic, but we must
        # preserve the original signature so FastMCP can generate the tool schema correctly.
        import functools

        @functools.wraps(handler)
        async def wrapped_tool(*args: Any, **kwargs: Any) -> Any:
            # Authorization might come from minder_authorization in MCP CallTool params
            authorization = kwargs.pop("minder_authorization", None)
            
            # Reconstruct arguments for call_tool
            sig = inspect.signature(handler)
            bound = sig.bind_partial(*args, **kwargs)
            return await self.call_tool(
                name,
                arguments=bound.arguments,
                authorization=authorization,
            )

        # Modify the signature of wrapped_tool to remove 'user' parameter
        # so FastMCP doesn't try to validate its presence in client requests.
        orig_sig = inspect.signature(handler)
        new_params = [
            p for p in orig_sig.parameters.values() 
            if p.name != "user"
        ]
        # Inject minder_authorization into the signature so FastMCP doesn't strip it.
        new_params.append(
            inspect.Parameter(
                "minder_authorization",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=str | None,
            )
        )
        wrapped_tool.__signature__ = orig_sig.replace(parameters=new_params)  # type: ignore

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
        
        # 1. Try context first (set by middleware or previous call in same task)
        context_user = get_current_user()
        if context_user is not None:
            logger.info(f"BaseTransport: found user in context: {context_user.email}")
            return context_user

        # 2. Fallback to explicit authorization header if provided
        if self._middleware is None:
            logger.error("BaseTransport: Transport requires auth but no AuthService was configured")
            raise RuntimeError("Transport requires auth but no AuthService was configured")
        
        logger.debug(f"BaseTransport: no user in context, checking header: {authorization[:10] if authorization else 'None'}")
        user = await self._middleware.authenticate(authorization)
        if user:
            logger.info(f"BaseTransport: authenticated from header: {user.email}")
        return user


async def _invoke(handler: ToolHandler, **kwargs: Any) -> Any:
    result = handler(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result
