from __future__ import annotations

import uuid

from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from minder.observability.metrics import get_metrics_summary

from .context import ADMIN_COOKIE_NAME, AdminRouteContext


def build_admin_api_routes(context: AdminRouteContext) -> list[BaseRoute]:
    def _public_base_url(request) -> str:
        return str(request.base_url).rstrip("/")

    async def setup_api(request):
        if await context.use_cases.has_admin_users():
            return JSONResponse({"error": "Admin already set up"}, status_code=403)
        payload = await request.json()
        username = str(payload.get("username", "")).strip()
        email = str(payload.get("email", "")).strip()
        display_name = str(payload.get("display_name", "")).strip()
        password = str(payload.get("password", "")).strip() or None
        if not all([username, email, display_name]):
            return JSONResponse({"error": "All fields are required."}, status_code=400)
        try:
            result = await context.use_cases.create_initial_admin(
                username=username,
                email=email,
                display_name=display_name,
                password=password,
            )
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(result, status_code=201)

    async def dashboard_login_api(request):
        """Accept either username+password or api_key authentication."""
        payload = await request.json()

        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()
        api_key = str(payload.get("api_key", "")).strip()

        if not (username and password) and not api_key:
            return JSONResponse(
                {"error": "Provide username + password, or an admin API key."},
                status_code=400,
            )

        try:
            if username and password:
                result = await context.use_cases.login_admin_by_password(username, password)
            else:
                result = await context.use_cases.login_admin(api_key)
        except PermissionError:
            return JSONResponse({"error": "Admin role required."}, status_code=403)
        except Exception:
            return JSONResponse({"error": "Invalid credentials."}, status_code=401)

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

    async def dashboard_bootstrap_state(request):
        has_admin_users = await context.use_cases.has_admin_users()
        has_admin_session = False
        if has_admin_users:
            try:
                await context.admin_user_from_request(request)
            except Exception:
                has_admin_session = False
            else:
                has_admin_session = True
        return JSONResponse(
            {
                "has_admin_users": has_admin_users,
                "has_admin_session": has_admin_session,
            }
        )

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
            result = await context.use_cases.test_client_connection(
                payload["client_api_key"],
                public_base_url=_public_base_url(request),
            )
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

    async def admin_tools(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        return JSONResponse({"tools": context.use_cases.list_tools()})

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
            updated = await context.use_cases.update_client(
                client_id=client_id,
                name=payload.get("name"),
                description=payload.get("description"),
                repo_scopes=payload.get("repo_scopes"),
                tool_scopes=payload.get("tool_scopes"),
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
            result = await context.use_cases.get_onboarding(
                client_id,
                public_base_url=_public_base_url(request),
            )
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
        try:
            limit = int(request.query_params.get("limit", "50"))
            offset = int(request.query_params.get("offset", "0"))
        except ValueError:
            limit, offset = 50, 0
        limit = max(1, min(limit, 200))  # cap at 200
        offset = max(0, offset)
        return JSONResponse(
            await context.use_cases.list_audit(actor_id=actor_id, limit=limit, offset=offset)
        )

    # ------------------------------------------------------------------
    # User management
    # ------------------------------------------------------------------

    async def admin_users(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        active_only = request.query_params.get("active_only", "false").lower() == "true"
        return JSONResponse(await context.use_cases.list_users(active_only=active_only))

    async def user_detail(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        user_id = uuid.UUID(str(request.path_params["user_id"]))

        if request.method == "GET":
            try:
                return JSONResponse(await context.use_cases.get_user_detail(user_id))
            except LookupError:
                return JSONResponse({"error": "User not found"}, status_code=404)

        if request.method == "PATCH":
            try:
                payload = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)
            try:
                return JSONResponse(
                    await context.use_cases.update_user(
                        user_id,
                        role=payload.get("role"),
                        is_active=payload.get("is_active"),
                        display_name=payload.get("display_name"),
                    )
                )
            except LookupError:
                return JSONResponse({"error": "User not found"}, status_code=404)
            except Exception as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)

        if request.method == "DELETE":
            try:
                return JSONResponse(await context.use_cases.deactivate_user(user_id))
            except LookupError:
                return JSONResponse({"error": "User not found"}, status_code=404)

        return JSONResponse({"error": "Method not allowed"}, status_code=405)

    # ------------------------------------------------------------------
    # Workflow management
    # ------------------------------------------------------------------

    async def admin_workflows(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        if request.method == "GET":
            return JSONResponse(await context.use_cases.list_workflows())

        if request.method == "POST":
            try:
                payload = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)
            name = str(payload.get("name", "")).strip()
            if not name:
                return JSONResponse({"error": "name is required"}, status_code=400)
            try:
                return JSONResponse(
                    await context.use_cases.create_workflow(
                        name=name,
                        description=str(payload.get("description", "")),
                        enforcement=str(payload.get("enforcement", "strict")),
                        steps=payload.get("steps"),
                    ),
                    status_code=201,
                )
            except Exception as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)

        return JSONResponse({"error": "Method not allowed"}, status_code=405)

    async def workflow_detail(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        workflow_id = uuid.UUID(str(request.path_params["workflow_id"]))

        if request.method == "GET":
            try:
                return JSONResponse(await context.use_cases.get_workflow_detail(workflow_id))
            except LookupError:
                return JSONResponse({"error": "Workflow not found"}, status_code=404)

        if request.method == "PATCH":
            try:
                payload = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)
            try:
                return JSONResponse(
                    await context.use_cases.update_workflow(
                        workflow_id,
                        name=payload.get("name"),
                        description=payload.get("description"),
                        enforcement=payload.get("enforcement"),
                        steps=payload.get("steps"),
                    )
                )
            except LookupError:
                return JSONResponse({"error": "Workflow not found"}, status_code=404)
            except Exception as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)

        if request.method == "DELETE":
            try:
                return JSONResponse(await context.use_cases.delete_workflow(workflow_id))
            except LookupError:
                return JSONResponse({"error": "Workflow not found"}, status_code=404)

        return JSONResponse({"error": "Method not allowed"}, status_code=405)

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    async def admin_metrics_summary(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        return JSONResponse(get_metrics_summary())

    # ------------------------------------------------------------------
    # Repository management
    # ------------------------------------------------------------------

    async def admin_repositories(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        return JSONResponse(await context.use_cases.list_repositories())

    return [
        Route("/v1/admin/setup", setup_api, methods=["POST"]),
        Route("/v1/admin/login", dashboard_login_api, methods=["POST"]),
        Route("/v1/admin/logout", dashboard_logout_api, methods=["POST"]),
        Route("/v1/admin/session", admin_session, methods=["GET"]),
        Route("/v1/admin/bootstrap-state", dashboard_bootstrap_state, methods=["GET"]),
        Route("/v1/auth/token-exchange", token_exchange, methods=["POST"]),
        Route("/v1/gateway/test-connection", gateway_test_connection, methods=["POST"]),
        Route("/v1/admin/tools", admin_tools, methods=["GET"]),
        Route("/v1/admin/clients", admin_clients, methods=["GET", "POST"]),
        Route("/v1/admin/clients/{client_id:uuid}", client_detail, methods=["GET", "PATCH"]),
        Route("/v1/admin/clients/{client_id:uuid}/keys", client_key_rotate, methods=["POST"]),
        Route("/v1/admin/clients/{client_id:uuid}/keys/revoke", client_key_revoke, methods=["POST"]),
        Route("/v1/admin/onboarding/{client_id:uuid}", client_onboarding, methods=["GET"]),
        Route("/v1/admin/audit", admin_audit, methods=["GET"]),
        # User management
        Route("/v1/admin/users", admin_users, methods=["GET"]),
        Route("/v1/admin/users/{user_id:uuid}", user_detail, methods=["GET", "PATCH", "DELETE"]),
        # Workflow management
        Route("/v1/admin/workflows", admin_workflows, methods=["GET", "POST"]),
        Route("/v1/admin/workflows/{workflow_id:uuid}", workflow_detail, methods=["GET", "PATCH", "DELETE"]),
        # Repository management
        Route("/v1/admin/repositories", admin_repositories, methods=["GET"]),
        # Observability
        Route("/v1/admin/metrics-summary", admin_metrics_summary, methods=["GET"]),
    ]
