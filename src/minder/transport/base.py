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
from minder.config import MinderConfig
from minder.auth.context import get_current_principal
from minder.store.interfaces import ICacheProvider, IOperationalStore
from minder.tools.registry import ALWAYS_AVAILABLE_FOR_CLIENTS

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
        cache_provider: ICacheProvider,
        store: IOperationalStore | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._middleware = AuthMiddleware(auth_service) if auth_service is not None else None
        self._rate_limiter = RateLimiter(cache=cache_provider, config=config)
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
        # New parameters to inject (must be before VAR_KEYWORD if present)
        injected = [
            inspect.Parameter(
                "minder_authorization",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=str | None,
            ),
            inspect.Parameter(
                "minder_client_key",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=str | None,
            ),
        ]

        final_params = []
        var_kw = None
        for p in new_params:
            if p.kind == inspect.Parameter.VAR_KEYWORD:
                var_kw = p
            else:
                final_params.append(p)

        final_params.extend(injected)
        if var_kw:
            final_params.append(var_kw)

        wrapped_tool.__signature__ = orig_sig.replace(parameters=final_params)  # type: ignore

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
        import time
        start = time.perf_counter()
        outcome = "error"
        principal = None
        _exc: Exception | None = None
        try:
            effective_client_key = client_key or self._default_client_key()
            principal = await self._authenticate_if_required(registered, authorization, effective_client_key)
            if principal is not None:
                if (
                    isinstance(principal, ClientPrincipal)
                    and name not in ALWAYS_AVAILABLE_FOR_CLIENTS
                    and name not in principal.scopes
                ):
                    outcome = "denied"
                    raise AuthError(
                        "AUTH_FORBIDDEN",
                        f"Client is not allowed to call tool '{name}'",
                    )
                if self._rate_limiter.enabled():
                    await self._rate_limiter.enforce(principal=principal, tool_name=name)
                kwargs["principal"] = principal
                if isinstance(principal, AdminUserPrincipal) and principal.user is not None:
                    kwargs["user"] = principal.user

            outcome = "success"
            return await _invoke(registered.handler, **kwargs)
        except Exception as exc:
            _exc = exc
            if isinstance(exc, AuthError):
                outcome = "denied"
            elif outcome == "success":
                outcome = "error"
            raise
        finally:
            elapsed = time.perf_counter() - start

            client_id = "unknown"
            actor_id = "unknown"
            actor_type = "unknown"
            if principal is not None:
                client_id = getattr(principal, "client_slug") if hasattr(principal, "client_slug") else "unknown"
                actor_id = str(principal.principal_id)
                actor_type = principal.principal_type

            # Record metrics (Prometheus - in-memory)
            try:
                from minder.observability.metrics import record_tool_call
                record_tool_call(name, outcome, elapsed, client_id=client_id)
            except Exception:
                pass

            # Record audit log (Persistent)
            if self._store is not None:
                try:
                    meta: dict[str, Any] = {
                        "client_id": client_id,
                        "latency_ms": round(elapsed * 1000, 2),
                        "arguments": arguments,
                    }
                    if _exc is not None:
                        meta["error_type"] = type(_exc).__name__
                        meta["error_message"] = str(_exc)
                    await self._store.create_audit_log(
                        actor_type=actor_type,
                        actor_id=actor_id,
                        event_type="tool_call",
                        tool_name=name,
                        resource_type="tool",
                        resource_id=name,
                        outcome=outcome,
                        audit_metadata=meta,
                    )
                except Exception:
                    pass

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
