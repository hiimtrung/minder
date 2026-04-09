from __future__ import annotations

import uuid

from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from .context import ADMIN_COOKIE_NAME, AdminRouteContext


def build_admin_api_routes(context: AdminRouteContext) -> list[BaseRoute]:
    async def setup_api(request):
        if await context.use_cases.has_admin_users():
            return JSONResponse({"error": "Admin already set up"}, status_code=403)
        payload = await request.json()
        username = str(payload.get("username", "")).strip()
        email = str(payload.get("email", "")).strip()
        display_name = str(payload.get("display_name", "")).strip()
        if not all([username, email, display_name]):
            return JSONResponse({"error": "All fields are required."}, status_code=400)
        try:
            result = await context.use_cases.create_initial_admin(
                username=username,
                email=email,
                display_name=display_name,
            )
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(result, status_code=201)

    async def dashboard_login_api(request):
        payload = await request.json()
        api_key = str(payload.get("api_key", "")).strip()
        if not api_key:
            return JSONResponse({"error": "Admin API key is required."}, status_code=400)
        try:
            result = await context.use_cases.login_admin(api_key)
        except PermissionError:
            return JSONResponse({"error": "Admin role required."}, status_code=403)
        except Exception:
            return JSONResponse({"error": "Invalid admin API key."}, status_code=401)

        response = JSONResponse({"ok": True}, status_code=200)
        response.set_cookie(
            ADMIN_COOKIE_NAME,
            result["jwt"],
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
            max_age=context.config.auth.jwt_expiry_hours * 3600,
        )
        return response

    async def dashboard_logout_api(request):
        del request
        response = JSONResponse({"ok": True}, status_code=200)
        response.delete_cookie(ADMIN_COOKIE_NAME, path="/")
        return response

    async def admin_session(request):
        try:
            user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        return JSONResponse({"admin": context.use_cases.serialize_admin_session(user)})

    async def token_exchange(request):
        payload = await request.json()
        exchange = await context.use_cases.exchange_client_key(
            client_api_key=payload["client_api_key"],
            requested_scopes=payload.get("requested_scopes"),
        )
        return JSONResponse(exchange)

    async def gateway_test_connection(request):
        payload = await request.json()
        try:
            result = await context.use_cases.test_client_connection(payload["client_api_key"])
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        return JSONResponse(result)

    async def list_clients(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        return JSONResponse(await context.use_cases.list_clients())

    async def create_client(request):
        try:
            user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        payload = await request.json()
        created = await context.use_cases.create_client(
            actor_user_id=user.id,
            name=payload["name"],
            slug=payload["slug"],
            description=payload.get("description", ""),
            tool_scopes=payload.get("tool_scopes"),
            repo_scopes=payload.get("repo_scopes"),
        )
        return JSONResponse(created, status_code=201)

    async def admin_clients(request):
        if request.method == "GET":
            return await list_clients(request)
        return await create_client(request)

    async def client_detail(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        client_id = uuid.UUID(str(request.path_params["client_id"]))
        if request.method == "GET":
            try:
                return JSONResponse(await context.use_cases.get_client_detail(client_id))
            except LookupError:
                return JSONResponse({"error": "Client not found"}, status_code=404)

        payload = await request.json()
        try:
            current = await context.use_cases.get_client_detail(client_id)
            updated = await context.use_cases.update_client(
                client_id=client_id,
                description=payload.get("description", current["client"]["description"]),
                repo_scopes=payload.get("repo_scopes", current["client"]["repo_scopes"]),
                tool_scopes=payload.get("tool_scopes", current["client"]["tool_scopes"]),
            )
        except LookupError:
            return JSONResponse({"error": "Client not found"}, status_code=404)
        return JSONResponse(updated)

    async def client_key_rotate(request):
        try:
            user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        client_id = uuid.UUID(str(request.path_params["client_id"]))
        try:
            result = await context.use_cases.issue_client_key(
                client_id=client_id,
                actor_user_id=user.id,
            )
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        return JSONResponse(result, status_code=201)

    async def client_key_revoke(request):
        try:
            user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        client_id = uuid.UUID(str(request.path_params["client_id"]))
        return JSONResponse(
            await context.use_cases.revoke_client_keys(client_id=client_id, actor_user_id=user.id)
        )

    async def client_onboarding(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        client_id = uuid.UUID(str(request.path_params["client_id"]))
        try:
            result = await context.use_cases.get_onboarding(client_id)
        except LookupError:
            return JSONResponse({"error": "Client not found"}, status_code=404)
        return JSONResponse(result)

    async def admin_audit(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        actor_id = request.query_params.get("actor_id")
        return JSONResponse(await context.use_cases.list_audit(actor_id=actor_id))

    return [
        Route("/v1/admin/setup", setup_api, methods=["POST"]),
        Route("/v1/admin/login", dashboard_login_api, methods=["POST"]),
        Route("/v1/admin/logout", dashboard_logout_api, methods=["POST"]),
        Route("/v1/admin/session", admin_session, methods=["GET"]),
        Route("/v1/auth/token-exchange", token_exchange, methods=["POST"]),
        Route("/v1/gateway/test-connection", gateway_test_connection, methods=["POST"]),
        Route("/v1/admin/clients", admin_clients, methods=["GET", "POST"]),
        Route("/v1/admin/clients/{client_id:uuid}", client_detail, methods=["GET", "PATCH"]),
        Route("/v1/admin/clients/{client_id:uuid}/keys", client_key_rotate, methods=["POST"]),
        Route("/v1/admin/clients/{client_id:uuid}/keys/revoke", client_key_revoke, methods=["POST"]),
        Route("/v1/admin/onboarding/{client_id:uuid}", client_onboarding, methods=["GET"]),
        Route("/v1/admin/audit", admin_audit, methods=["GET"]),
    ]
