from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, PlainTextResponse, RedirectResponse
from starlette.routing import BaseRoute, Route

from minder.config import MinderConfig
from minder.observability.logging import AccessLogMiddleware, CorrelationIdMiddleware
from minder.observability.metrics import metrics_endpoint
from minder.store.interfaces import ICacheProvider, IOperationalStore

from .api import build_admin_api_routes
from .context import AdminRouteContext
from .dashboard import build_dashboard_routes


DEFAULT_DASHBOARD_DEV_ORIGIN = "http://localhost:8808"


def _favicon_path() -> Path:
    return Path(__file__).resolve().parents[5] / "favicon.png"


def dashboard_dev_origin(config: MinderConfig) -> str | None:
    dev_server_url = (config.dashboard.dev_server_url or "").strip()
    if not dev_server_url:
        return DEFAULT_DASHBOARD_DEV_ORIGIN
    parts = urlsplit(dev_server_url)
    if not parts.scheme or not parts.netloc:
        return DEFAULT_DASHBOARD_DEV_ORIGIN
    return f"{parts.scheme}://{parts.netloc}"


def build_http_routes(
    *,
    config: MinderConfig,
    store: IOperationalStore,
    cache: ICacheProvider | None = None,
) -> list[BaseRoute]:
    context = AdminRouteContext.build(config=config, store=store, cache=cache)

    async def favicon_png(_request) -> FileResponse | PlainTextResponse:
        favicon = _favicon_path()
        if favicon.is_file():
            return FileResponse(favicon, media_type="image/png")
        return PlainTextResponse("favicon not found", status_code=404)

    async def favicon_ico(_request) -> RedirectResponse:
        return RedirectResponse(url="/favicon.png", status_code=308)

    return [
        Route("/favicon.ico", favicon_ico, methods=["GET"]),
        Route("/favicon.png", favicon_png, methods=["GET"]),
        Route("/metrics", metrics_endpoint, methods=["GET"]),
        *build_admin_api_routes(context),
        *build_dashboard_routes(context),
    ]


def build_http_app(
    *,
    config: MinderConfig,
    store: IOperationalStore,
    cache: ICacheProvider | None = None,
) -> Starlette:
    middleware: list[Middleware] = []

    # Observability middleware (innermost first — applied outermost-last)
    middleware.append(Middleware(CorrelationIdMiddleware))
    middleware.append(Middleware(AccessLogMiddleware))

    dev_origin = dashboard_dev_origin(config)
    if dev_origin:
        middleware.append(
            Middleware(
                CORSMiddleware,
                allow_origins=[dev_origin],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        )
    return Starlette(
        routes=build_http_routes(config=config, store=store, cache=cache),
        middleware=middleware,
    )
