from __future__ import annotations

from urllib.parse import urlsplit

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import BaseRoute

from minder.config import MinderConfig
from minder.store.interfaces import ICacheProvider, IOperationalStore

from .api import build_admin_api_routes
from .context import AdminRouteContext
from .dashboard import build_dashboard_routes


def dashboard_dev_origin(config: MinderConfig) -> str | None:
    dev_server_url = (config.dashboard.dev_server_url or "").strip()
    if not dev_server_url:
        return None
    parts = urlsplit(dev_server_url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def build_http_routes(
    *,
    config: MinderConfig,
    store: IOperationalStore,
    cache: ICacheProvider | None = None,
) -> list[BaseRoute]:
    context = AdminRouteContext.build(config=config, store=store, cache=cache)
    return [
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
