from __future__ import annotations

from starlette.applications import Starlette
from starlette.routing import BaseRoute

from minder.config import MinderConfig
from minder.store.interfaces import ICacheProvider, IOperationalStore

from .api import build_admin_api_routes
from .context import AdminRouteContext
from .dashboard import build_dashboard_routes


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
    return Starlette(routes=build_http_routes(config=config, store=store, cache=cache))
