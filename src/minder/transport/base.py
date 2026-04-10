import logging
import inspect
from dataclasses import dataclass
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from minder.auth.middleware import AuthMiddleware
from minder.auth.service import AuthError
from minder.auth.rate_limiter import RateLimiter
from minder.auth.principal import AdminUserPrincipal, ClientPrincipal, Principal
from minder.auth.service import AuthService
from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
from minder.auth.context import get_current_principal
from minder.store.interfaces import ICacheProvider

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

    def __init__(
        self,
        *,
        config: MinderConfig,
        auth_service: AuthService | None = None,
        cache_provider: ICacheProvider | None = None,
    ) -> None:
        self._config = config
        self._middleware = AuthMiddleware(auth_service) if auth_service is not None else None
        effective_cache = cache_provider or LRUCacheProvider(
            max_size=config.cache.max_size,
            default_ttl=max(config.cache.ttl_seconds, config.rate_limit.window_seconds),
        )
        self._rate_limiter = RateLimiter(cache=effective_cache, config=config)
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
        effective_description = description or inspect.getdoc(handler) or self._describe_tool(name)
        self._tools[name] = RegisteredTool(
            name=name,
            handler=handler,
            require_auth=require_auth,
            description=effective_description,
        )

        # We need to wrap the handler to inject auth logic, but we must
        # preserve the original signature so FastMCP can generate the tool schema correctly.
        import functools

        @functools.wraps(handler)
        async def wrapped_tool(*args: Any, **kwargs: Any) -> Any:
            # Authorization might come from minder_authorization in MCP CallTool params
            authorization = kwargs.pop("minder_authorization", None)
            client_key = kwargs.pop("minder_client_key", None)
            
            # Reconstruct arguments for call_tool
            sig = inspect.signature(handler)
            bound = sig.bind_partial(*args, **kwargs)
            return await self.call_tool(
                name,
                arguments=bound.arguments,
                authorization=authorization,
                client_key=client_key,
            )

        # Modify the signature of wrapped_tool to remove 'user' parameter
        # so FastMCP doesn't try to validate its presence in client requests.
        orig_sig = inspect.signature(handler)
        new_params = [
            p for p in orig_sig.parameters.values() 
            if p.name not in {"user", "principal"}
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
        new_params.append(
            inspect.Parameter(
                "minder_client_key",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=str | None,
            )
        )
        wrapped_tool.__signature__ = orig_sig.replace(parameters=new_params)  # type: ignore

        self._server.add_tool(
            wrapped_tool,
            name=name,
            description=effective_description,
            structured_output=False,
        )

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def _default_client_key(self) -> str | None:
        return None

    async def call_tool(
        self,
        name: str,
        *,
        arguments: dict[str, Any] | None = None,
        authorization: str | None = None,
        client_key: str | None = None,
    ) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")

        registered = self._tools[name]
        kwargs = dict(arguments or {})
        effective_client_key = client_key or self._default_client_key()
        principal = await self._authenticate_if_required(registered, authorization, effective_client_key)
        if principal is not None:
            if isinstance(principal, ClientPrincipal) and name not in principal.scopes:
                raise AuthError(
                    "AUTH_FORBIDDEN",
                    f"Client is not allowed to call tool '{name}'",
                )
            if self._rate_limiter.enabled():
                await self._rate_limiter.enforce(principal=principal, tool_name=name)
            kwargs["principal"] = principal
            if isinstance(principal, AdminUserPrincipal) and principal.user is not None:
                kwargs["user"] = principal.user
        return await _invoke(registered.handler, **kwargs)

    @staticmethod
    def _describe_tool(name: str) -> str:
        words = name.replace("minder_", "").replace("_", " ")
        return f"Run the {words} tool in Minder."

    async def _authenticate_if_required(
        self,
        registered: RegisteredTool,
        authorization: str | None,
        client_key: str | None,
    ) -> Principal | None:
        if not registered.require_auth:
            return None
        
        # 1. Try context first (set by middleware or previous call in same task)
        context_principal = get_current_principal()
        if context_principal is not None:
            logger.info(
                "BaseTransport: found principal in context: %s",
                context_principal.principal_type,
            )
            return context_principal

        # 2. Fallback to explicit authorization header if provided
        if self._middleware is None:
            logger.error("BaseTransport: Transport requires auth but no AuthService was configured")
            raise RuntimeError("Transport requires auth but no AuthService was configured")
        
        logger.debug(
            "BaseTransport: no principal in context, checking auth header/client key",
        )
        principal = await self._middleware.authenticate_principal(
            authorization,
            client_key=client_key,
        )
        logger.info(
            "BaseTransport: authenticated principal from request: %s",
            principal.principal_type,
        )
        return principal


async def _invoke(handler: ToolHandler, **kwargs: Any) -> Any:
    signature = inspect.signature(handler)
    accepts_var_kw = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if accepts_var_kw:
        filtered_kwargs = kwargs
    else:
        filtered_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in signature.parameters
        }
    result = handler(**filtered_kwargs)
    if inspect.isawaitable(result):
        return await result
    return result
