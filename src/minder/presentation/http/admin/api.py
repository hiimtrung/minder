from __future__ import annotations

import logging
import uuid
from urllib.parse import urlsplit

from pydantic import ValidationError
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from minder.application.admin.dto import (
    ClientRepositoryResolveRequest,
    GraphSyncRequest,
    UpsertRepositoryBranchLinkRequest,
)
from minder.auth.principal import ClientPrincipal
from minder.observability.metrics import (
    get_metrics_summary,
    record_admin_operation,
    record_auth_event,
)

from .context import ADMIN_COOKIE_NAME, AdminRouteContext

logger = logging.getLogger(__name__)


def _normalize_repository_remote(repo_url: str | None) -> str | None:
    if repo_url is None:
        return None
    raw_url = str(repo_url).strip()
    if not raw_url:
        return None
    if raw_url.startswith("git@"):
        host_and_path = raw_url[4:]
        host, separator, path = host_and_path.partition(":")
        if separator and host and path:
            normalized_path = path.strip().lstrip("/").removesuffix(".git")
            if normalized_path:
                return f"git@{host}:{normalized_path}.git"
        return raw_url
    if (
        raw_url.startswith("ssh://")
        or raw_url.startswith("http://")
        or raw_url.startswith("https://")
    ):
        parts = urlsplit(raw_url)
        host = parts.hostname or ""
        path = parts.path.strip().lstrip("/").removesuffix(".git")
        user = parts.username or "git"
        if host and path:
            return f"{user}@{host}:{path}.git"
    return raw_url.rstrip("/")


def _principal_can_access_candidates(
    principal: ClientPrincipal,
    candidates: list[str],
) -> bool:
    scopes = [
        scope.strip() for scope in principal.repo_scope if scope and scope.strip()
    ]
    if not scopes:
        return False
    if "*" in scopes:
        return True
    normalized_candidates = [
        candidate.rstrip("/") for candidate in candidates if candidate
    ]
    for scope in scopes:
        normalized_scope = scope.rstrip("/")
        for candidate in normalized_candidates:
            if candidate == normalized_scope:
                return True
            if candidate.startswith(f"{normalized_scope}/"):
                return True
    return False


def _repository_scope_candidates(
    repository: object, payload: GraphSyncRequest
) -> list[str]:
    candidates: list[str] = []
    repo_name = getattr(repository, "repo_name", None)
    if repo_name:
        candidates.append(str(repo_name))
    repo_url = getattr(repository, "repo_url", None)
    normalized_repo_url = _normalize_repository_remote(repo_url)
    if normalized_repo_url:
        candidates.append(normalized_repo_url)
    payload_remote = _normalize_repository_remote(
        payload.sync_metadata.get("repo_remote")
        if isinstance(payload.sync_metadata, dict)
        else None
    )
    if payload_remote:
        candidates.append(payload_remote)
    return [candidate for candidate in candidates if candidate]


def _principal_can_access_repository(
    principal: ClientPrincipal,
    repository: object,
    payload: GraphSyncRequest,
) -> bool:
    return _principal_can_access_candidates(
        principal,
        _repository_scope_candidates(repository, payload),
    )


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
                result = await context.use_cases.login_admin_by_password(
                    username, password
                )
            else:
                result = await context.use_cases.login_admin(api_key)
        except PermissionError:
            await record_auth_event(
                "login", "denied", client_id="dashboard", store=context.store
            )
            return JSONResponse({"error": "Admin role required."}, status_code=403)
        except Exception:
            await record_auth_event(
                "login", "failure", client_id="dashboard", store=context.store
            )
            return JSONResponse({"error": "Invalid credentials."}, status_code=401)

        await record_auth_event(
            "login", "success", client_id="dashboard", store=context.store
        )
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
        await record_auth_event(
            "logout", "success", client_id="dashboard", store=context.store
        )
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
        try:
            exchange = await context.use_cases.exchange_client_key(
                client_api_key=payload["client_api_key"],
                requested_scopes=payload.get("requested_scopes"),
            )
        except Exception as exc:
            await record_auth_event("token_exchange", "failure", store=context.store)
            return JSONResponse({"error": str(exc)}, status_code=401)
        client_slug = str(exchange.get("client_slug", "unknown"))
        await record_auth_event(
            "token_exchange", "success", client_id=client_slug, store=context.store
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
        try:
            created = await context.use_cases.create_client(
                actor_user_id=user.id,
                name=payload["name"],
                slug=payload["slug"],
                description=payload.get("description", ""),
                tool_scopes=payload.get("tool_scopes"),
                repo_scopes=payload.get("repo_scopes"),
            )
        except Exception as exc:
            await record_admin_operation(
                "create_client", "error", actor_id=str(user.id), store=context.store
            )
            return JSONResponse({"error": str(exc)}, status_code=400)
        await record_admin_operation(
            "create_client", "success", actor_id=str(user.id), store=context.store
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
            user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        client_id = uuid.UUID(str(request.path_params["client_id"]))
        if request.method == "GET":
            try:
                return JSONResponse(
                    await context.use_cases.get_client_detail(client_id)
                )
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
            await record_admin_operation(
                "update_client", "error", actor_id=str(user.id), store=context.store
            )
            return JSONResponse({"error": "Client not found"}, status_code=404)
        except Exception:
            await record_admin_operation(
                "update_client", "error", actor_id=str(user.id), store=context.store
            )
            raise

        await record_admin_operation(
            "update_client", "success", actor_id=str(user.id), store=context.store
        )
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
            await record_admin_operation(
                "key_rotate", "error", actor_id=str(user.id), store=context.store
            )
            return JSONResponse({"error": str(exc)}, status_code=404)
        await record_admin_operation(
            "key_rotate", "success", actor_id=str(user.id), store=context.store
        )
        return JSONResponse(result, status_code=201)

    async def client_key_revoke(request):
        try:
            user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        client_id = uuid.UUID(str(request.path_params["client_id"]))
        try:
            result = await context.use_cases.revoke_client_keys(
                client_id=client_id, actor_user_id=user.id
            )
            await record_admin_operation(
                "key_revoke", "success", actor_id=str(user.id), store=context.store
            )
            return JSONResponse(result)
        except Exception:
            await record_admin_operation(
                "key_revoke", "error", actor_id=str(user.id), store=context.store
            )
            raise

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
        # Allow filtering by client_id as an alias for actor_id
        actor_id = (
            request.query_params.get("client_id")
            or request.query_params.get("actor_id")
            or None
        )
        event_type = request.query_params.get("event_type") or None
        outcome = request.query_params.get("outcome") or None
        try:
            limit = int(request.query_params.get("limit", "50"))
            offset = int(request.query_params.get("offset", "0"))
        except ValueError:
            limit, offset = 50, 0
        limit = max(1, min(limit, 200))  # cap at 200
        offset = max(0, offset)
        return JSONResponse(
            await context.use_cases.list_audit(
                actor_id=actor_id,
                event_type=event_type,
                outcome=outcome,
                limit=limit,
                offset=offset,
            )
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

        if request.method == "POST":
            try:
                payload = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)

            username = str(payload.get("username", "")).strip()
            email = str(payload.get("email", "")).strip()
            display_name = str(payload.get("display_name", "")).strip()
            role = str(payload.get("role", "admin")).strip() or "admin"
            password = str(payload.get("password", "")).strip() or None

            if not username or not email or not display_name:
                return JSONResponse(
                    {"error": "username, email, and display_name are required"},
                    status_code=400,
                )

            try:
                return JSONResponse(
                    await context.use_cases.create_user(
                        username=username,
                        email=email,
                        display_name=display_name,
                        role=role,
                        password=password,
                    ),
                    status_code=201,
                )
            except Exception as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)

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
                return JSONResponse(
                    await context.use_cases.get_workflow_detail(workflow_id)
                )
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
                return JSONResponse(
                    await context.use_cases.delete_workflow(workflow_id)
                )
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

        try:
            active_sessions = await context.store.count_active_client_sessions()
        except Exception as exc:
            logger.warning("Failed to count active client sessions: %s", exc)
            active_sessions = None

        client_id = request.query_params.get("client_id")
        event_type = request.query_params.get("event_type")
        outcome = request.query_params.get("outcome")

        summary = await get_metrics_summary(
            store=context.store,
            active_sessions=active_sessions,
            client_id=client_id,
            event_type=event_type,
            outcome=outcome,
        )
        return JSONResponse(summary)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def admin_sessions(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        return JSONResponse(await context.use_cases.list_sessions())

    async def session_detail(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        session_id = uuid.UUID(str(request.path_params["session_id"]))
        if request.method == "GET":
            try:
                return JSONResponse(
                    await context.use_cases.get_session_detail(session_id)
                )
            except LookupError:
                return JSONResponse({"error": "Session not found"}, status_code=404)

        if request.method == "DELETE":
            try:
                return JSONResponse(await context.use_cases.delete_session(session_id))
            except LookupError:
                return JSONResponse({"error": "Session not found"}, status_code=404)

        return JSONResponse({"error": "Method not allowed"}, status_code=405)

    # ------------------------------------------------------------------
    # Repository management

    async def admin_repositories(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        return JSONResponse(await context.use_cases.list_repositories())

    async def repository_landscape(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        return JSONResponse(await context.use_cases.list_repository_landscape())

    async def repository_detail(request):
        try:
            user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        repo_id = uuid.UUID(str(request.path_params["repo_id"]))
        if request.method == "GET":
            try:
                return JSONResponse(
                    await context.use_cases.get_repository_detail(repo_id)
                )
            except LookupError:
                return JSONResponse({"error": "Repository not found"}, status_code=404)

        if request.method == "PATCH":
            payload = await request.json()
            try:
                result = await context.use_cases.update_repository(
                    repo_id=repo_id,
                    name=payload.get("name"),
                    remote_url=payload.get("remote_url"),
                    default_branch=payload.get("default_branch"),
                    path=payload.get("path"),
                )
            except LookupError:
                await record_admin_operation(
                    "repository_update",
                    "error",
                    actor_id=str(user.id),
                    store=context.store,
                )
                return JSONResponse({"error": "Repository not found"}, status_code=404)
            except ValueError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)

            await record_admin_operation(
                "repository_update",
                "success",
                actor_id=str(user.id),
                store=context.store,
            )
            return JSONResponse(result)

        try:
            result = await context.use_cases.delete_repository(repo_id)
        except LookupError:
            await record_admin_operation(
                "repository_delete", "error", actor_id=str(user.id), store=context.store
            )
            return JSONResponse({"error": "Repository not found"}, status_code=404)

        await record_admin_operation(
            "repository_delete", "success", actor_id=str(user.id), store=context.store
        )
        return JSONResponse(result)

    async def repository_graph_map(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        repo_id = uuid.UUID(str(request.path_params["repo_id"]))
        branch = (request.query_params.get("branch") or "").strip() or None
        node_types = [
            value.strip()
            for value in request.query_params.getlist("node_type")
            if value.strip()
        ]
        try:
            return JSONResponse(
                await context.use_cases.get_repository_graph_map(
                    repo_id=repo_id,
                    branch=branch,
                    node_types=node_types or None,
                )
            )
        except LookupError:
            return JSONResponse({"error": "Repository not found"}, status_code=404)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)

    async def repository_node_neighborhood(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        repo_id = uuid.UUID(str(request.path_params["repo_id"]))
        node_id_raw = str(request.path_params["node_id"])
        try:
            node_id = uuid.UUID(node_id_raw)
        except ValueError:
            # Handle non-UUID nodes (like folders)
            return JSONResponse({"error": f"Node ID '{node_id_raw}' is not a valid UUID. Neighborhood exploration is only supported for persisted graph nodes."}, status_code=400)
        try:
            depth = int(request.query_params.get("depth", "4"))
            limit = int(request.query_params.get("limit", "200"))
        except ValueError:
            return JSONResponse({"error": "Invalid depth or limit"}, status_code=400)

        try:
            return JSONResponse(
                await context.use_cases.get_repository_node_neighborhood(
                    repo_id=repo_id,
                    node_id=node_id,
                    depth=depth,
                    limit=limit,
                )
            )
        except LookupError:
            return JSONResponse({"error": "Repository not found"}, status_code=404)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)

    async def repository_graph_summary(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        repo_id = uuid.UUID(str(request.path_params["repo_id"]))
        branch = (request.query_params.get("branch") or "").strip() or None
        try:
            return JSONResponse(
                await context.use_cases.get_repository_graph_summary(
                    repo_id=repo_id, branch=branch
                )
            )
        except LookupError:
            return JSONResponse({"error": "Repository not found"}, status_code=404)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)

    async def repository_graph_search(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        repo_id = uuid.UUID(str(request.path_params["repo_id"]))
        query = (request.query_params.get("query") or "").strip()
        if not query:
            return JSONResponse({"error": "Query is required"}, status_code=400)
        branch = (request.query_params.get("branch") or "").strip() or None
        node_types = [
            value.strip()
            for value in request.query_params.getlist("node_type")
            if value.strip()
        ]
        languages = [
            value.strip()
            for value in request.query_params.getlist("language")
            if value.strip()
        ]
        last_states = [
            value.strip()
            for value in request.query_params.getlist("last_state")
            if value.strip()
        ]
        try:
            limit = max(1, min(int(request.query_params.get("limit", "10")), 50))
        except ValueError:
            return JSONResponse({"error": "Invalid limit"}, status_code=400)

        try:
            return JSONResponse(
                await context.use_cases.search_repository_graph(
                    repo_id=repo_id,
                    query=query,
                    branch=branch,
                    node_types=node_types or None,
                    languages=languages or None,
                    last_states=last_states or None,
                    limit=limit,
                )
            )
        except LookupError:
            return JSONResponse({"error": "Repository not found"}, status_code=404)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)

    async def repository_graph_impact(request):
        try:
            await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        repo_id = uuid.UUID(str(request.path_params["repo_id"]))
        target = (request.query_params.get("target") or "").strip()
        if not target:
            return JSONResponse({"error": "Target is required"}, status_code=400)
        branch = (request.query_params.get("branch") or "").strip() or None
        try:
            depth = max(1, min(int(request.query_params.get("depth", "2")), 6))
            limit = max(1, min(int(request.query_params.get("limit", "25")), 100))
        except ValueError:
            return JSONResponse({"error": "Invalid depth or limit"}, status_code=400)

        try:
            return JSONResponse(
                await context.use_cases.get_repository_graph_impact(
                    repo_id=repo_id,
                    target=target,
                    branch=branch,
                    depth=depth,
                    limit=limit,
                )
            )
        except LookupError:
            return JSONResponse({"error": "Repository not found"}, status_code=404)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)

    # ------------------------------------------------------------------
    # Branch management
    # ------------------------------------------------------------------

    async def repository_branches(request):
        try:
            user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        repo_id = uuid.UUID(str(request.path_params["repo_id"]))

        if request.method == "GET":
            try:
                return JSONResponse(
                    await context.use_cases.list_repository_branches(repo_id=repo_id)
                )
            except LookupError:
                return JSONResponse({"error": "Repository not found"}, status_code=404)

        if request.method == "POST":
            try:
                payload = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)
            branch = str(payload.get("branch", "")).strip()
            if not branch:
                return JSONResponse({"error": "branch is required"}, status_code=400)
            try:
                result = await context.use_cases.add_repository_branch(
                    repo_id=repo_id, branch=branch
                )
                await record_admin_operation(
                    "repository_branch_add",
                    "success",
                    actor_id=str(user.id),
                    store=context.store,
                )
                return JSONResponse(result, status_code=201)
            except LookupError:
                return JSONResponse({"error": "Repository not found"}, status_code=404)
            except ValueError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)

        return JSONResponse({"error": "Method not allowed"}, status_code=405)

    async def repository_branch_delete(request):
        try:
            user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        repo_id = uuid.UUID(str(request.path_params["repo_id"]))
        branch = str(request.path_params.get("branch", "")).strip()
        if not branch:
            return JSONResponse({"error": "branch is required"}, status_code=400)
        try:
            result = await context.use_cases.remove_repository_branch(
                repo_id=repo_id, branch=branch
            )
            await record_admin_operation(
                "repository_branch_remove",
                "success",
                actor_id=str(user.id),
                store=context.store,
            )
            return JSONResponse(result)
        except LookupError:
            return JSONResponse({"error": "Repository not found"}, status_code=404)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def repository_branch_links(request):
        try:
            user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        repo_id = uuid.UUID(str(request.path_params["repo_id"]))
        branch = (request.query_params.get("branch") or "").strip() or None

        if request.method == "GET":
            try:
                return JSONResponse(
                    await context.use_cases.list_repository_branch_links(
                        repo_id=repo_id,
                        branch=branch,
                    )
                )
            except LookupError:
                return JSONResponse({"error": "Repository not found"}, status_code=404)

        try:
            payload = UpsertRepositoryBranchLinkRequest.model_validate(
                await request.json()
            )
        except ValidationError as exc:
            return JSONResponse(
                {
                    "error": "Invalid repository branch link payload",
                    "details": exc.errors(),
                },
                status_code=400,
            )

        try:
            result = await context.use_cases.upsert_repository_branch_link(
                repo_id=repo_id,
                source_branch=payload.source_branch,
                target_repo_id=payload.target_repo_id,
                target_repo_name=payload.target_repo_name,
                target_repo_url=payload.target_repo_url,
                target_branch=payload.target_branch,
                relation=payload.relation,
                direction=payload.direction,
                confidence=payload.confidence,
                metadata=payload.metadata,
            )
            await record_admin_operation(
                "repository_branch_link_upsert",
                "success",
                actor_id=str(user.id),
                store=context.store,
            )
            return JSONResponse(result, status_code=201)
        except LookupError:
            return JSONResponse({"error": "Repository not found"}, status_code=404)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def repository_branch_link_delete(request):
        try:
            user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        repo_id = uuid.UUID(str(request.path_params["repo_id"]))
        link_id = str(request.path_params.get("link_id", "")).strip()
        branch = (request.query_params.get("branch") or "").strip() or None
        if not link_id:
            return JSONResponse({"error": "link_id is required"}, status_code=400)

        try:
            result = await context.use_cases.delete_repository_branch_link(
                repo_id=repo_id,
                link_id=link_id,
                branch=branch,
            )
            await record_admin_operation(
                "repository_branch_link_delete",
                "success",
                actor_id=str(user.id),
                store=context.store,
            )
            return JSONResponse(result)
        except LookupError as exc:
            status_code = (
                404 if "Repository" in str(exc) or "not found" in str(exc) else 400
            )
            return JSONResponse({"error": str(exc)}, status_code=status_code)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def repository_graph_sync(request):
        try:
            user = await context.admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        if context.graph_store is None:
            return JSONResponse(
                {"error": "Graph sync store is not configured"},
                status_code=503,
            )

        repo_id = uuid.UUID(str(request.path_params["repo_id"]))
        try:
            payload = GraphSyncRequest.model_validate(await request.json())
        except ValidationError as exc:
            return JSONResponse(
                {"error": "Invalid graph sync payload", "details": exc.errors()},
                status_code=400,
            )

        try:
            result = await context.use_cases.sync_repository_graph(
                repo_id=repo_id,
                payload=payload,
            )
        except LookupError:
            await record_admin_operation(
                "repository_graph_sync",
                "error",
                actor_id=str(user.id),
                store=context.store,
            )
            return JSONResponse({"error": "Repository not found"}, status_code=404)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)
        except Exception as exc:
            await record_admin_operation(
                "repository_graph_sync",
                "error",
                actor_id=str(user.id),
                store=context.store,
            )
            return JSONResponse({"error": str(exc)}, status_code=400)

        await record_admin_operation(
            "repository_graph_sync",
            "success",
            actor_id=str(user.id),
            store=context.store,
        )
        return JSONResponse(result, status_code=202)

    async def client_repository_graph_sync(request):
        try:
            principal = await context.client_principal_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Client principal required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        if context.graph_store is None:
            return JSONResponse(
                {"error": "Graph sync store is not configured"},
                status_code=503,
            )

        repo_id = uuid.UUID(str(request.path_params["repo_id"]))
        repository = await context.store.get_repository_by_id(repo_id)
        if repository is None:
            return JSONResponse({"error": "Repository not found"}, status_code=404)

        try:
            payload = GraphSyncRequest.model_validate(await request.json())
        except ValidationError as exc:
            return JSONResponse(
                {"error": "Invalid graph sync payload", "details": exc.errors()},
                status_code=400,
            )

        if not _principal_can_access_repository(principal, repository, payload):
            return JSONResponse(
                {"error": "Client is not allowed to sync this repository"},
                status_code=403,
            )

        try:
            result = await context.use_cases.sync_repository_graph(
                repo_id=repo_id,
                payload=payload,
            )
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        try:
            await context.store.create_audit_log(
                actor_type="client",
                actor_id=str(principal.client_id),
                event_type="repository.graph_sync",
                resource_type="repository",
                resource_id=str(repo_id),
                outcome="success",
                audit_metadata={
                    "client_slug": principal.client_slug,
                    "payload_version": payload.payload_version,
                    "source": payload.source,
                    "nodes_upserted": result["nodes_upserted"],
                    "edges_upserted": result["edges_upserted"],
                },
            )
        except Exception:
            logger.exception("Failed to record client graph sync audit log")

        return JSONResponse(result, status_code=202)

    async def client_repository_resolve(request):
        try:
            principal = await context.client_principal_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Client principal required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)

        try:
            payload = ClientRepositoryResolveRequest.model_validate(
                await request.json()
            )
        except ValidationError as exc:
            return JSONResponse(
                {
                    "error": "Invalid repository resolve payload",
                    "details": exc.errors(),
                },
                status_code=400,
            )

        candidates = [payload.repo_name, payload.repo_path]
        normalized_remote = _normalize_repository_remote(payload.repo_url)
        if normalized_remote:
            candidates.append(normalized_remote)

        if not _principal_can_access_candidates(principal, candidates):
            return JSONResponse(
                {"error": "Client is not allowed to resolve this repository"},
                status_code=403,
            )

        try:
            result = await context.use_cases.resolve_repository_for_client(
                repo_name=payload.repo_name,
                repo_path=payload.repo_path,
                repo_url=payload.repo_url,
                default_branch=payload.default_branch,
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        repository_id = result["repository"]["id"]
        try:
            await context.store.create_audit_log(
                actor_type="client",
                actor_id=str(principal.client_id),
                event_type="repository.resolve",
                resource_type="repository",
                resource_id=repository_id,
                outcome="success",
                audit_metadata={
                    "client_slug": principal.client_slug,
                    "created": result["created"],
                    "path": result["repository"]["path"],
                    "name": result["repository"]["name"],
                },
            )
        except Exception:
            logger.exception("Failed to record client repository resolve audit log")

        return JSONResponse(result, status_code=201 if result["created"] else 200)

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
        Route(
            "/v1/admin/clients/{client_id:uuid}",
            client_detail,
            methods=["GET", "PATCH"],
        ),
        Route(
            "/v1/admin/clients/{client_id:uuid}/keys",
            client_key_rotate,
            methods=["POST"],
        ),
        Route(
            "/v1/admin/clients/{client_id:uuid}/keys/revoke",
            client_key_revoke,
            methods=["POST"],
        ),
        Route(
            "/v1/admin/onboarding/{client_id:uuid}", client_onboarding, methods=["GET"]
        ),
        Route("/v1/admin/audit", admin_audit, methods=["GET"]),
        # User management
        Route("/v1/admin/users", admin_users, methods=["GET", "POST"]),
        Route(
            "/v1/admin/users/{user_id:uuid}",
            user_detail,
            methods=["GET", "PATCH", "DELETE"],
        ),
        # Workflow management
        Route("/v1/admin/workflows", admin_workflows, methods=["GET", "POST"]),
        Route(
            "/v1/admin/workflows/{workflow_id:uuid}",
            workflow_detail,
            methods=["GET", "PATCH", "DELETE"],
        ),
        # Session management
        Route("/v1/admin/sessions", admin_sessions, methods=["GET"]),
        Route(
            "/v1/admin/sessions/{session_id:uuid}",
            session_detail,
            methods=["GET", "DELETE"],
        ),
        # Repository management
        Route("/v1/admin/repositories", admin_repositories, methods=["GET"]),
        Route(
            "/v1/admin/repositories/landscape", repository_landscape, methods=["GET"]
        ),
        Route(
            "/v1/admin/repositories/{repo_id:uuid}",
            repository_detail,
            methods=["GET", "PATCH", "DELETE"],
        ),
        Route(
            "/v1/admin/repositories/{repo_id:uuid}/branches",
            repository_branches,
            methods=["GET", "POST"],
        ),
        Route(
            "/v1/admin/repositories/{repo_id:uuid}/branches/{branch:str}",
            repository_branch_delete,
            methods=["DELETE"],
        ),
        Route(
            "/v1/admin/repositories/{repo_id:uuid}/branch-links",
            repository_branch_links,
            methods=["GET", "POST"],
        ),
        Route(
            "/v1/admin/repositories/{repo_id:uuid}/branch-links/{link_id:str}",
            repository_branch_link_delete,
            methods=["DELETE"],
        ),
        Route(
            "/v1/admin/repositories/{repo_id:uuid}/graph-map",
            repository_graph_map,
            methods=["GET"],
        ),
        Route(
            "/v1/admin/repositories/{repo_id:uuid}/nodes/{node_id:str}/neighborhood",
            repository_node_neighborhood,
            methods=["GET"],
        ),
        Route(
            "/v1/admin/repositories/{repo_id:uuid}/graph-summary",
            repository_graph_summary,
            methods=["GET"],
        ),
        Route(
            "/v1/admin/repositories/{repo_id:uuid}/graph-search",
            repository_graph_search,
            methods=["GET"],
        ),
        Route(
            "/v1/admin/repositories/{repo_id:uuid}/graph-impact",
            repository_graph_impact,
            methods=["GET"],
        ),
        Route(
            "/v1/admin/repositories/{repo_id:uuid}/graph-sync",
            repository_graph_sync,
            methods=["POST"],
        ),
        Route(
            "/v1/client/repositories/resolve",
            client_repository_resolve,
            methods=["POST"],
        ),
        Route(
            "/v1/client/repositories/{repo_id:uuid}/graph-sync",
            client_repository_graph_sync,
            methods=["POST"],
        ),
        # Observability
        Route("/v1/admin/metrics-summary", admin_metrics_summary, methods=["GET"]),
    ]
