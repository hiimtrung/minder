from __future__ import annotations

from pathlib import Path

from starlette.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.routing import BaseRoute, Route

from .context import AdminRouteContext


def build_dashboard_routes(context: AdminRouteContext) -> list[BaseRoute]:
    def _dev_dashboard_url(asset_path: str = "") -> str | None:
        dev_server_url = (context.config.dashboard.dev_server_url or "").strip().rstrip("/")
        if not dev_server_url:
            return None
        if asset_path:
            return f"{dev_server_url}/{asset_path.strip('/')}"
        return dev_server_url

    async def dashboard_static(request):
        asset_path = str(request.path_params.get("asset_path", "")).strip("/")
        dev_target = _dev_dashboard_url(asset_path)
        if dev_target is not None:
            return RedirectResponse(url=dev_target, status_code=307)

        static_dir = Path(context.config.dashboard.static_dir).expanduser()

        async def _has_admin_session() -> bool:
            try:
                await context.admin_user_from_request(request)
            except Exception:
                return False
            return True

        has_admin_users = await context.use_cases.has_admin_users()
        has_admin_session = await _has_admin_session()
        is_asset_request = "." in Path(asset_path).name or asset_path.startswith("_astro/")

        if not is_asset_request:
            if not has_admin_users and asset_path not in {"setup"}:
                return RedirectResponse(url=f"{context.config.dashboard.base_path}/setup", status_code=303)
            if has_admin_users and asset_path == "setup":
                target = (
                    f"{context.config.dashboard.base_path}/clients"
                    if has_admin_session
                    else f"{context.config.dashboard.base_path}/login"
                )
                return RedirectResponse(url=target, status_code=303)
            if has_admin_users and not has_admin_session and asset_path not in {"login"}:
                return RedirectResponse(url=f"{context.config.dashboard.base_path}/login", status_code=303)
            if has_admin_users and has_admin_session and asset_path in {"", "login"}:
                return RedirectResponse(url=f"{context.config.dashboard.base_path}/clients", status_code=303)

        if not static_dir.exists():
            return HTMLResponse("Dashboard build not found", status_code=404)

        if not asset_path:
            candidates = [static_dir / "index.html"]
        else:
            requested = static_dir / asset_path
            candidates = [requested, requested / "index.html"]

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return FileResponse(candidate)

        if asset_path.startswith("clients/"):
            clients_index = static_dir / "clients" / "index.html"
            if clients_index.exists() and clients_index.is_file():
                return FileResponse(clients_index)

        fallback = static_dir / "index.html"
        if fallback.exists() and fallback.is_file():
            return FileResponse(fallback)
        return HTMLResponse("Dashboard build not found", status_code=404)

    async def console_compat_redirect(request):
        asset_path = str(request.path_params.get("asset_path", "")).strip("/")
        dev_target = _dev_dashboard_url(asset_path)
        if dev_target is not None:
            return RedirectResponse(url=dev_target, status_code=308)
        target = context.config.dashboard.base_path
        if asset_path:
            target = f"{target}/{asset_path}"
        return RedirectResponse(url=target, status_code=308)

    async def setup_redirect(_):
        dev_target = _dev_dashboard_url("setup")
        if dev_target is not None:
            return RedirectResponse(url=dev_target, status_code=308)
        return RedirectResponse(url=f"{context.config.dashboard.base_path}/setup", status_code=308)

    return [
        Route("/setup", setup_redirect, methods=["GET"]),
        Route("/console", console_compat_redirect, methods=["GET"]),
        Route("/console/{asset_path:path}", console_compat_redirect, methods=["GET"]),
        Route(f"{context.config.dashboard.base_path}", dashboard_static, methods=["GET"]),
        Route(f"{context.config.dashboard.base_path}" + "/{asset_path:path}", dashboard_static, methods=["GET"]),
    ]
