from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from minder.application.admin.dto import (
    ActivityEventPayload,
    AdminLoginPayload,
    AdminSessionPayload,
    AuditEventPayload,
    AuditListPayload,
    ClientConnectionTestPayload,
    ClientDetailPayload,
    ClientKeyPayload,
    ClientListPayload,
    ClientRepositoryResolvePayload,
    ClientPayload,
    CreateClientPayload,
    CreateUserPayload,
    GraphSyncRequest,
    GraphSyncResultPayload,
    OnboardingPayload,
    DeleteRepositoryPayload,
    RepositoryBranchLinkListPayload,
    RepositoryBranchLinkPayload,
    RepositoryBranchListPayload,
    RepositoryBranchPayload,
    RepositoryDetailPayload,
    RepositoryGraphEdgePayload,
    RepositoryGraphImpactPayload,
    RepositoryGraphMapPayload,
    RepositoryGraphNodePayload,
    RepositoryGraphSearchPayload,
    RepositoryGraphSummaryPayload,
    RepositoryLandscapePayload,
    RepositoryListPayload,
    RepositoryPayload,
    RevokeKeysPayload,
    SetupResultPayload,
    UserDetailPayload,
    UserListPayload,
    UserPayload,
    WorkflowDetailPayload,
    WorkflowListPayload,
    WorkflowPayload,
    WorkflowStepPayload,
)
from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.store.interfaces import IGraphRepository, IOperationalStore
from minder.tools.graph import GraphTools
from minder.tools.registry import SCOPEABLE_TOOLS

DASHBOARD_TOOL_SCOPE_OPTIONS = [tool.name for tool in SCOPEABLE_TOOLS]

DASHBOARD_TOOL_SCOPE_PRESETS: dict[str, list[str]] = {
    "Query Only": ["minder_query", "minder_search_code", "minder_search_errors"],
    "Read Only": [
        "minder_query",
        "minder_search_code",
        "minder_search_errors",
        "minder_search",
        "minder_memory_recall",
        "minder_workflow_get",
    ],
    "Full Dev Assistant": [
        "minder_query",
        "minder_search_code",
        "minder_search_errors",
        "minder_search",
        "minder_memory_recall",
        "minder_workflow_get",
        "minder_workflow_step",
    ],
}

logger = logging.getLogger(__name__)


class AdminConsoleUseCases:
    def __init__(
        self,
        *,
        store: IOperationalStore,
        auth_service: AuthService,
        config: MinderConfig,
        graph_store: IGraphRepository | None = None,
    ) -> None:
        self._store = store
        self._auth_service = auth_service
        self._config = config
        self._graph_store = graph_store
        self._graph_tools = GraphTools(graph_store, store)

    async def has_admin_users(self) -> bool:
        return await self._auth_service.has_admin_users()

    async def create_initial_admin(
        self,
        *,
        username: str,
        email: str,
        display_name: str,
        password: str | None = None,
    ) -> SetupResultPayload:
        _user, api_key = await self._auth_service.register_user(
            email=email,
            username=username,
            display_name=display_name,
            role="admin",
            password=password,
        )
        return {"api_key": api_key}

    async def login_admin(self, api_key: str) -> AdminLoginPayload:
        """Authenticate via admin API key (``mk_...`` format)."""
        user = await self._auth_service.authenticate_api_key(api_key)
        if user.role != "admin":
            raise PermissionError("Admin role required")
        return {"jwt": self._auth_service.issue_jwt(user)}

    async def login_admin_by_password(
        self, username: str, password: str
    ) -> AdminLoginPayload:
        """Authenticate via username + password."""
        user = await self._auth_service.authenticate_username_password(
            username, password
        )
        if user.role != "admin":
            raise PermissionError("Admin role required")
        return {"jwt": self._auth_service.issue_jwt(user)}

    async def set_user_password(self, user_id: uuid.UUID, password: str) -> None:
        """Set or replace the login password for any user."""
        await self._auth_service.set_password(user_id, password)

    @staticmethod
    def serialize_admin_session(user: Any) -> AdminSessionPayload:
        return {
            "id": str(user.id),
            "username": str(user.username),
            "email": str(user.email),
            "display_name": str(user.display_name),
            "role": str(user.role),
        }

    async def exchange_client_key(
        self,
        *,
        client_api_key: str,
        requested_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._auth_service.exchange_client_api_key(
            client_api_key,
            requested_scopes=requested_scopes,
        )

    def list_tools(self) -> list[dict[str, str]]:
        """Return all tools that can be granted to client principals."""
        return [
            {"name": tool.name, "description": tool.description}
            for tool in SCOPEABLE_TOOLS
        ]

    async def list_clients(self) -> ClientListPayload:
        return {
            "clients": [
                self.serialize_client(client)
                for client in await self._store.list_clients()
            ]
        }

    async def create_client(
        self,
        *,
        actor_user_id: uuid.UUID,
        name: str,
        slug: str,
        description: str = "",
        tool_scopes: list[str] | None = None,
        repo_scopes: list[str] | None = None,
    ) -> CreateClientPayload:
        client, client_api_key = await self._auth_service.register_client(
            name=name,
            slug=slug,
            description=description,
            created_by_user_id=actor_user_id,
            tool_scopes=tool_scopes,
            repo_scopes=repo_scopes,
        )
        return {
            "client": self.serialize_client(client),
            "client_api_key": client_api_key,
        }

    async def get_client_detail(self, client_id: uuid.UUID) -> ClientDetailPayload:
        client = await self._store.get_client_by_id(client_id)
        if client is None:
            raise LookupError("Client not found")
        return {"client": self.serialize_client(client)}

    async def update_client(
        self,
        *,
        client_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        repo_scopes: list[str] | None = None,
        tool_scopes: list[str] | None = None,
    ) -> ClientDetailPayload:
        kwargs: dict[str, Any] = {}
        if name is not None:
            kwargs["name"] = name
        if description is not None:
            kwargs["description"] = description
        if repo_scopes is not None:
            kwargs["repo_scopes"] = repo_scopes
        if tool_scopes is not None:
            kwargs["tool_scopes"] = tool_scopes
        updated = await self._store.update_client(client_id, **kwargs)
        if updated is None:
            raise LookupError("Client not found")
        return {"client": self.serialize_client(updated)}

    async def issue_client_key(
        self,
        *,
        client_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> ClientKeyPayload:
        client_api_key = await self._auth_service.create_client_api_key(
            client_id=client_id,
            created_by_user_id=actor_user_id,
        )
        return {"client_api_key": client_api_key}

    async def revoke_client_keys(
        self,
        *,
        client_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> RevokeKeysPayload:
        await self._auth_service.revoke_client_api_keys(
            client_id, actor_user_id=actor_user_id
        )
        return {"revoked": True}

    async def get_onboarding(
        self,
        client_id: uuid.UUID,
        *,
        public_base_url: str | None = None,
    ) -> OnboardingPayload:
        client = await self._store.get_client_by_id(client_id)
        if client is None:
            raise LookupError("Client not found")
        return {
            "client": self.serialize_client(client),
            "templates": self.onboarding_templates(
                client, public_base_url=public_base_url
            ),
        }

    async def test_client_connection(
        self,
        client_api_key: str,
        *,
        public_base_url: str | None = None,
    ) -> ClientConnectionTestPayload:
        client = await self._auth_service.authenticate_client_api_key(client_api_key)
        return {
            "ok": True,
            "client": self.serialize_client(client),
            "templates": self.onboarding_templates(
                client, public_base_url=public_base_url
            ),
        }

    async def list_audit(
        self,
        *,
        actor_id: str | None = None,
        event_type: str | None = None,
        outcome: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditListPayload:
        events = await self._store.list_audit_logs(
            actor_id=actor_id,
            event_type=event_type,
            outcome=outcome,
            limit=limit,
            offset=offset,
        )
        total = await self._store.count_audit_logs(
            actor_id=actor_id,
            event_type=event_type,
            outcome=outcome,
        )
        serialized = [
            await self.serialize_audit_event_enriched(event) for event in events
        ]
        return {"events": serialized, "total": total, "limit": limit, "offset": offset}

    async def get_recent_client_activity(
        self,
        client_id: uuid.UUID,
        *,
        limit: int = 8,
    ) -> list[ActivityEventPayload]:
        events = await self._store.list_audit_logs()
        filtered = [
            event
            for event in events
            if str(getattr(event, "resource_id", "")) == str(client_id)
        ]
        filtered.sort(
            key=lambda event: getattr(event, "created_at", None) or "", reverse=True
        )
        return [
            {
                "event_type": str(getattr(event, "event_type", "")),
                "created_at": (
                    getattr(event, "created_at").isoformat()
                    if getattr(event, "created_at", None)
                    else "unknown time"
                ),
            }
            for event in filtered[:limit]
        ]

    async def list_repo_scope_candidates(self) -> list[str]:
        candidates = ["*", "/workspace/repo", "/workspace/docs"]
        clients = await self._store.list_clients()
        for client in clients:
            candidates.extend(list(getattr(client, "repo_scopes", [])))
        return self.dedupe_preserve_order(candidates)

    def onboarding_templates(
        self, client: Any, *, public_base_url: str | None = None
    ) -> dict[str, str]:
        base_url = (
            public_base_url.rstrip("/")
            if public_base_url
            else f"http://localhost:{self._config.server.port}"
        )
        return {
            "codex": (
                "[mcp_servers.minder]\n"
                f'url = "{base_url}/sse"\n'
                'http_headers = { "X-Minder-Client-Key" = "<mkc_...>" }'
            ),
            "vscode": (
                f'{{"servers":{{"minder":{{"type":"sse","url":"{base_url}/sse","headers":{{"X-Minder-Client-Key":"<mkc_...>"}}}}}},"inputs":[]}}'
            ),
            "copilot_cli": (
                f'{{"mcpServers":{{"minder":{{"type":"sse","url":"{base_url}/sse","headers":{{"X-Minder-Client-Key":"<mkc_...>"}},"tools":["*"]}}}}}}'
            ),
            "antigravity": (
                f'{{"mcpServers":{{"minder":{{"serverUrl":"{base_url}/mcp","headers":{{"X-Minder-Client-Key":"<mkc_...>"}}}}}}}}'
            ),
            "cursor": (
                f'{{"mcpServers":{{"minder":{{"url":"{base_url}/mcp","headers":{{"X-Minder-Client-Key":"<mkc_...>"}}}}}}}}'
            ),
            "claude_code": (
                f'{{"mcpServers":{{"minder":{{"type":"sse","url":"{base_url}/sse","headers":{{"X-Minder-Client-Key":"<mkc_...>"}}}}}}}}'
            ),
        }

    @staticmethod
    def split_csv(raw: str) -> list[str]:
        return [item.strip() for item in raw.split(",") if item.strip()]

    @staticmethod
    def dedupe_preserve_order(values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                deduped.append(value)
        return deduped

    @staticmethod
    def serialize_client(client: Any) -> ClientPayload:
        return {
            "id": str(client.id),
            "name": client.name,
            "slug": client.slug,
            "description": getattr(client, "description", ""),
            "status": client.status,
            "tool_scopes": list(client.tool_scopes),
            "repo_scopes": list(client.repo_scopes),
            "workflow_scopes": list(getattr(client, "workflow_scopes", [])),
            "transport_modes": list(getattr(client, "transport_modes", [])),
        }

    @staticmethod
    def serialize_audit_event(event: Any) -> AuditEventPayload:
        return {
            "id": str(event.id),
            "actor_type": event.actor_type,
            "actor_id": event.actor_id,
            "actor_name": None,
            "event_type": event.event_type,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "resource_name": None,
            "outcome": event.outcome,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }

    async def serialize_audit_event_enriched(self, event: Any) -> AuditEventPayload:
        """Like serialize_audit_event but resolves human-readable names."""
        base = self.serialize_audit_event(event)

        # Resolve actor name
        try:
            if event.actor_type == "admin_user":
                actor = await self._store.get_user_by_id(uuid.UUID(event.actor_id))
                if actor:
                    base["actor_name"] = getattr(
                        actor, "display_name", None
                    ) or getattr(actor, "username", None)
            elif event.actor_type == "client":
                actor_client = await self._store.get_client_by_id(
                    uuid.UUID(event.actor_id)
                )
                if actor_client:
                    base["actor_name"] = getattr(actor_client, "name", None)
        except Exception:
            pass

        # Resolve resource name
        try:
            if event.resource_type == "client":
                resource_client = await self._store.get_client_by_id(
                    uuid.UUID(event.resource_id)
                )
                if resource_client:
                    base["resource_name"] = getattr(resource_client, "name", None)
            elif event.resource_type == "user":
                resource_user = await self._store.get_user_by_id(
                    uuid.UUID(event.resource_id)
                )
                if resource_user:
                    base["resource_name"] = getattr(
                        resource_user, "display_name", None
                    ) or getattr(resource_user, "username", None)
        except Exception:
            pass

        return base

    # ------------------------------------------------------------------
    # User management
    # ------------------------------------------------------------------

    async def list_users(self, *, active_only: bool = False) -> UserListPayload:
        users = await self._store.list_users(active_only=active_only)
        return {"users": [self.serialize_user(u) for u in users]}

    async def create_user(
        self,
        *,
        username: str,
        email: str,
        display_name: str,
        role: str = "admin",
        password: str | None = None,
    ) -> CreateUserPayload:
        user, api_key = await self._auth_service.register_user(
            email=email,
            username=username,
            display_name=display_name,
            role=role,
            password=password,
        )
        return {"user": self.serialize_user(user), "api_key": api_key}

    async def get_user_detail(self, user_id: uuid.UUID) -> UserDetailPayload:
        user = await self._store.get_user_by_id(user_id)
        if user is None:
            raise LookupError(f"User {user_id} not found")
        # Include MCP clients created by this user
        all_clients = await self._store.list_clients()
        owned_clients = [
            self.serialize_client(c)
            for c in all_clients
            if str(getattr(c, "created_by_user_id", "")) == str(user_id)
        ]
        return {"user": self.serialize_user(user), "clients": owned_clients}

    async def update_user(
        self,
        user_id: uuid.UUID,
        *,
        role: str | None = None,
        is_active: bool | None = None,
        display_name: str | None = None,
    ) -> UserDetailPayload:
        kwargs: dict[str, Any] = {}
        if role is not None:
            kwargs["role"] = role
        if is_active is not None:
            kwargs["is_active"] = is_active
        if display_name is not None:
            kwargs["display_name"] = display_name
        updated = await self._store.update_user(user_id, **kwargs)
        if updated is None:
            raise LookupError(f"User {user_id} not found")
        return await self.get_user_detail(user_id)

    async def deactivate_user(self, user_id: uuid.UUID) -> UserDetailPayload:
        await self._store.update_user(user_id, is_active=False)
        return await self.get_user_detail(user_id)

    @staticmethod
    def serialize_user(user: Any) -> UserPayload:
        return {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "display_name": getattr(user, "display_name", user.username),
            "role": user.role,
            "is_active": bool(getattr(user, "is_active", True)),
            "created_at": (
                user.created_at.isoformat()
                if getattr(user, "created_at", None)
                else None
            ),
        }

    # ------------------------------------------------------------------
    # Workflow management
    # ------------------------------------------------------------------

    async def list_workflows(self) -> WorkflowListPayload:
        workflows = await self._store.list_workflows()
        return {"workflows": [self.serialize_workflow(w) for w in workflows]}

    async def get_workflow_detail(
        self, workflow_id: uuid.UUID
    ) -> WorkflowDetailPayload:
        workflow = await self._store.get_workflow_by_id(workflow_id)
        if workflow is None:
            raise LookupError(f"Workflow {workflow_id} not found")
        return {"workflow": self.serialize_workflow(workflow)}

    async def create_workflow(
        self,
        *,
        name: str,
        description: str = "",
        enforcement: str = "strict",
        steps: list[dict[str, Any]] | None = None,
    ) -> WorkflowDetailPayload:
        workflow = await self._store.create_workflow(
            id=uuid.uuid4(),
            name=name,
            description=description,
            enforcement=enforcement,
            steps=steps or [],
        )
        return {"workflow": self.serialize_workflow(workflow)}

    async def update_workflow(
        self,
        workflow_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        enforcement: str | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> WorkflowDetailPayload:
        kwargs: dict[str, Any] = {}
        if name is not None:
            kwargs["name"] = name
        if description is not None:
            kwargs["description"] = description
        if enforcement is not None:
            kwargs["enforcement"] = enforcement
        if steps is not None:
            kwargs["steps"] = steps
        updated = await self._store.update_workflow(workflow_id, **kwargs)
        if updated is None:
            raise LookupError(f"Workflow {workflow_id} not found")
        return {"workflow": self.serialize_workflow(updated)}

    async def delete_workflow(self, workflow_id: uuid.UUID) -> dict[str, bool]:
        existing = await self._store.get_workflow_by_id(workflow_id)
        if existing is None:
            raise LookupError(f"Workflow {workflow_id} not found")
        await self._store.delete_workflow(workflow_id)
        return {"deleted": True}

    @staticmethod
    def serialize_workflow(workflow: Any) -> WorkflowPayload:
        raw_steps = getattr(workflow, "steps", []) or []
        steps: list[WorkflowStepPayload] = [
            {
                "name": s.get("name", "") if isinstance(s, dict) else str(s),
                "description": s.get("description", "") if isinstance(s, dict) else "",
                "gate": s.get("gate", None) if isinstance(s, dict) else None,
            }
            for s in raw_steps
        ]
        return {
            "id": str(workflow.id),
            "name": workflow.name,
            "description": getattr(workflow, "description", ""),
            "enforcement": getattr(workflow, "enforcement", "strict"),
            "steps": steps,
            "created_at": (
                workflow.created_at.isoformat()
                if getattr(workflow, "created_at", None)
                else None
            ),
        }

    # ------------------------------------------------------------------
    # Repository management
    # ------------------------------------------------------------------

    async def list_repositories(self) -> RepositoryListPayload:
        repos = await self._store.list_repositories()
        result: list[RepositoryPayload] = []
        for repo in repos:
            state = None
            try:
                state = await self._store.get_workflow_state_by_repo(repo.id)
            except Exception:
                pass
            result.append(self.serialize_repository(repo, state))
        return {"repositories": result}

    async def get_repository_detail(
        self, repo_id: uuid.UUID
    ) -> RepositoryDetailPayload:
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        state = None
        try:
            state = await self._store.get_workflow_state_by_repo(repo_id)
        except Exception:
            state = None
        return {"repository": self.serialize_repository(repository, state)}

    async def update_repository(
        self,
        *,
        repo_id: uuid.UUID,
        name: str | None = None,
        remote_url: str | None = None,
        default_branch: str | None = None,
        path: str | None = None,
    ) -> RepositoryDetailPayload:
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        updates: dict[str, Any] = {}
        if name is not None:
            normalized_name = str(name).strip()
            if not normalized_name:
                raise ValueError("Repository name is required")
            updates["repo_name"] = normalized_name
        if remote_url is not None:
            normalized_remote = _normalize_repository_remote(remote_url)
            if normalized_remote is None:
                raise ValueError("Repository remote URL is required")
            updates["repo_url"] = normalized_remote
        if default_branch is not None:
            normalized_branch = str(default_branch).strip()
            if not normalized_branch:
                raise ValueError("Default branch is required")
            updates["default_branch"] = normalized_branch
        if path is not None:
            normalized_path = str(path).strip()
            if not normalized_path:
                raise ValueError("Repository path is required")
            updates["state_path"] = normalized_path

        updated = await self._store.update_repository(repo_id, **updates)
        if updated is None:
            raise LookupError("Repository not found")
        return await self.get_repository_detail(repo_id)

    async def delete_repository(self, repo_id: uuid.UUID) -> DeleteRepositoryPayload:
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")
        await self._store.delete_repository(repo_id)
        return {"deleted": True}

    async def resolve_repository_for_client(
        self,
        *,
        repo_name: str,
        repo_path: str,
        repo_url: str | None = None,
        default_branch: str | None = None,
    ) -> ClientRepositoryResolvePayload:
        normalized_url = _normalize_repository_remote(repo_url)
        if normalized_url is None:
            raise ValueError(
                "Repository remote SSH URL is required for repository resolution"
            )

        normalized_name = _repo_name_from_remote(normalized_url) or repo_name.strip()
        normalized_path = repo_path.strip().rstrip("/")
        normalized_branch = (default_branch or "").strip() or "main"

        if not normalized_name:
            raise ValueError("Repository name is required")
        if not normalized_path:
            raise ValueError("Repository path is required")

        repository = await self._find_repository_for_client_sync(
            repo_name=normalized_name,
            repo_path=normalized_path,
            repo_url=normalized_url,
        )
        state_path = str(Path(normalized_path) / self._config.workflow.repo_state_dir)
        created = False

        if repository is None:
            repository = await self._store.create_repository(
                repo_name=normalized_name,
                repo_url=normalized_url,
                default_branch=normalized_branch,
                state_path=state_path,
            )
            created = True
        else:
            updates: dict[str, Any] = {}
            existing_remote = _normalize_repository_remote(
                getattr(repository, "repo_url", None)
            )
            if existing_remote != normalized_url:
                updates["repo_url"] = normalized_url
            if not str(getattr(repository, "state_path", "") or "").strip() and state_path:
                updates["state_path"] = state_path
            if (
                normalized_branch
                and str(getattr(repository, "default_branch", "") or "")
                != normalized_branch
            ):
                updates["default_branch"] = normalized_branch
            if updates:
                repository = (
                    await self._store.update_repository(repository.id, **updates)
                    or repository
                )

        return {
            "repository": self.serialize_repository(repository),
            "created": created,
            "last_sync": self._repository_last_sync(repository),
        }

    @staticmethod
    def serialize_repository(repo: Any, state: Any = None) -> RepositoryPayload:
        raw_branches = getattr(repo, "tracked_branches", None)
        tracked: list[str] = (
            list(raw_branches) if isinstance(raw_branches, list) else []
        )
        return {
            "id": str(repo.id),
            "name": getattr(repo, "repo_name", getattr(repo, "name", "")),
            "path": getattr(repo, "state_path", getattr(repo, "path", "")),
            "remote_url": _normalize_repository_remote(getattr(repo, "repo_url", None)),
            "default_branch": getattr(repo, "default_branch", None),
            "tracked_branches": tracked,
            "workflow_name": getattr(state, "workflow_name", None) if state else None,
            "workflow_state": getattr(state, "state", None) if state else None,
            "current_step": getattr(state, "current_step", None) if state else None,
            "created_at": (
                repo.created_at.isoformat()
                if getattr(repo, "created_at", None)
                else None
            ),
        }

    async def sync_repository_graph(
        self,
        *,
        repo_id: uuid.UUID,
        payload: GraphSyncRequest,
    ) -> GraphSyncResultPayload:
        if self._graph_store is None:
            raise RuntimeError("Graph sync store is not configured")

        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        repo_name = getattr(
            repository, "repo_name", getattr(repository, "name", str(repo_id))
        )
        repo_remote = _normalize_repository_remote(
            getattr(repository, "repo_url", None)
        )
        branch = payload.branch or getattr(repository, "default_branch", None)
        accepted_at = datetime.now(UTC).isoformat()
        node_ids: dict[tuple[str, str], uuid.UUID] = {}
        deleted_nodes = 0
        nodes_upserted = 0
        edges_upserted = 0
        
        # --- Check for redundant sync using commit_hash ---
        relationships = dict(getattr(repository, "relationships", {}) or {})
        graph_sync = dict(relationships.get("graph_sync", {}) or {})
        last_sync = dict(graph_sync.get("last_sync", {}) or {})
        
        if (
            payload.commit_hash 
            and payload.commit_hash == last_sync.get("commit_hash")
            and not payload.nodes 
            and not payload.edges
            and not payload.deleted_files
        ):
            return {
                "repo_id": str(repo_id),
                "repository_name": repo_name,
                "payload_version": payload.payload_version,
                "source": payload.source,
                "branch": branch,
                "deleted_nodes": 0,
                "nodes_upserted": 0,
                "edges_upserted": 0,
                "accepted_at": accepted_at,
            }
 
        # --- Scoped deletion: prune stale nodes for changed/deleted files ---
        changed_files = payload.changed_files
        paths_to_prune: set[str] = set(payload.deleted_files)
        if isinstance(changed_files, list):
            paths_to_prune.update(
                str(p) for p in changed_files if isinstance(p, str) and p.strip()
            )
        paths_to_prune.update(
            str(node.metadata.get("path"))
            for node in payload.nodes
            if isinstance(node.metadata.get("path"), str)
            and str(node.metadata.get("path")).strip()
        )

        if paths_to_prune:
            # Use efficient scoped deletion (v2) or fallback to full scan
            if hasattr(self._graph_store, "delete_nodes_by_scope"):
                deleted_nodes = await self._graph_store.delete_nodes_by_scope(
                    repo_id=str(repo_id),
                    branch=branch,
                    paths=paths_to_prune,
                )
            else:
                for graph_node in await self._graph_store.list_nodes():
                    metadata = dict(graph_node.extra_metadata or {})
                    if metadata.get("repo_id") != str(repo_id):
                        continue
                    if branch is not None and metadata.get("branch") not in {
                        None,
                        branch,
                    }:
                        continue
                    if str(metadata.get("path", "") or "") not in paths_to_prune:
                        continue
                    await self._graph_store.delete_node(graph_node.id)
                    deleted_nodes += 1

        # --- Upsert nodes with proper repo/branch scope (v2) ---
        _branch = branch or ""
        _repo_id_str = str(repo_id)
        
        # We strip large collections from sync_metadata before broadcasting to nodes
        _filtered_sync_meta = {
            k: v for k, v in payload.sync_metadata.items()
            if k not in {"changed_files", "deleted_files"}
        }

        _common_meta = {
            "repo_id": _repo_id_str,
            "repository_name": repo_name,
            "repository_remote": repo_remote,
            "source": payload.source,
            "payload_version": payload.payload_version,
            "branch": _branch,
            "repo_path": payload.repo_path,
            "diff_base": payload.diff_base,
            **_filtered_sync_meta,
        }
        _edge_common_meta = {
            "repo_id": _repo_id_str,
            "repository_name": repo_name,
            "repository_remote": repo_remote,
            "source": payload.source,
            "payload_version": payload.payload_version,
            "branch": _branch,
            "repo_path": payload.repo_path,
        }

        # --- Bulk upsert nodes ---
        # Use a dict to deduplicate nodes by (type, name)
        deduped_nodes: dict[tuple[str, str], dict[str, Any]] = {}
        
        for node in payload.nodes:
            key = (node.node_type, node.name)
            deduped_nodes[key] = {
                "node_type": node.node_type,
                "name": node.name,
                "metadata": {**_common_meta, **node.metadata},
            }
        
        # Also need to collect nodes mentioned in edges that might not be in payload.nodes
        for edge in payload.edges:
            for side in [edge.source, edge.target]:
                key = (side.node_type, side.name)
                if key not in deduped_nodes:
                    deduped_nodes[key] = {
                        "node_type": side.node_type,
                        "name": side.name,
                        "metadata": _edge_common_meta,
                    }
        
        node_ids = await self._graph_store.bulk_upsert_nodes(
            list(deduped_nodes.values()),
            repo_id=_repo_id_str,
            branch=_branch,
        )
        nodes_upserted = len(deduped_nodes)

        # --- Bulk upsert edges ---
        deduped_edges: dict[tuple[uuid.UUID, uuid.UUID, str], dict[str, Any]] = {}
        for edge in payload.edges:
            source_id = node_ids.get((edge.source.node_type, edge.source.name))
            target_id = node_ids.get((edge.target.node_type, edge.target.name))
            if source_id and target_id:
                edge_key = (source_id, target_id, edge.relation)
                deduped_edges[edge_key] = {
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation": edge.relation,
                    "weight": edge.weight,
                }
        
        edges_upserted = await self._graph_store.bulk_upsert_edges(
            list(deduped_edges.values()),
            repo_id=_repo_id_str,
        )

        # --- Update repository: tracked_branches + graph_sync metadata ---
        relationships = dict(getattr(repository, "relationships", {}) or {})
        graph_sync_state = {
            "payload_version": payload.payload_version,
            "source": payload.source,
            "branch": branch,
            "repo_path": payload.repo_path,
            "repo_remote": repo_remote,
            "diff_base": payload.diff_base,
            "deleted_files": payload.deleted_files,
            "commit_hash": payload.commit_hash,
            "deleted_nodes": deleted_nodes,
            "nodes_upserted": nodes_upserted,
            "edges_upserted": edges_upserted,
            "accepted_at": accepted_at,
        }
        graph_sync["last_sync"] = graph_sync_state
        graph_sync.update(graph_sync_state)
        branch_registry = dict(graph_sync.get("branches", {}) or {})
        if branch:
            branch_registry[branch] = graph_sync_state
        graph_sync["branches"] = branch_registry
        relationships["graph_sync"] = graph_sync

        cross_repo_links = self._repository_branch_links(repository)
        if payload.branch_relationships:
            repositories = await self._store.list_repositories()
            cross_repo_links = self._merge_branch_links(
                cross_repo_links,
                self._build_branch_links(
                    repository=repository,
                    repositories=repositories,
                    source_branch=branch,
                    accepted_at=accepted_at,
                    source=payload.source,
                    specs=[
                        {
                            "source_branch": relationship.source_branch,
                            "target_repo_id": relationship.target_repo_id,
                            "target_repo_name": relationship.target_repo_name,
                            "target_repo_url": relationship.target_repo_url,
                            "target_branch": relationship.target_branch,
                            "relation": relationship.relation,
                            "direction": relationship.direction,
                            "confidence": relationship.confidence,
                            "metadata": relationship.metadata,
                        }
                        for relationship in payload.branch_relationships
                    ],
                ),
            )
            relationships["cross_repo_branches"] = cross_repo_links

        # Auto-register branch in tracked_branches on first sync
        raw_branches = list(getattr(repository, "tracked_branches", None) or [])
        if branch:
            if branch not in raw_branches:
                raw_branches.append(branch)
        await self._store.update_repository(
            repo_id,
            relationships=relationships,
            tracked_branches=raw_branches,
        )

        # Auto-prune stale branches that are no longer tracked
        await self.prune_repository_stale_data(repo_id)

        return {
            "repo_id": str(repo_id),
            "repository_name": repo_name,
            "payload_version": payload.payload_version,
            "source": payload.source,
            "branch": branch,
            "deleted_nodes": deleted_nodes,
            "nodes_upserted": nodes_upserted,
            "edges_upserted": edges_upserted,
            "accepted_at": accepted_at,
        }

    async def get_repository_graph_summary(
        self,
        *,
        repo_id: uuid.UUID,
        branch: str | None = None,
    ) -> RepositoryGraphSummaryPayload:
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        repository_payload = self.serialize_repository(repository)
        effective_branch = branch or getattr(repository, "default_branch", None) or None
        branch_state = self._repository_branch_state_payload(
            repository, effective_branch
        )
        branch_links = await self.list_repository_branch_links(
            repo_id=repo_id, branch=effective_branch
        )
        if self._graph_store is None:
            return {
                "repository": repository_payload,
                "graph_available": False,
                "active_branch": effective_branch,
                "branch_state": branch_state,
                "branch_links": branch_links["links"],
                "last_sync": self._repository_last_sync(repository),
                "node_count": 0,
                "counts_by_type": {},
                "routes": [],
                "todos": [],
                "external_services": [],
                "dependencies": [],
            }

        repo_nodes = await self._repository_graph_nodes(repository, branch=branch)
        counts = Counter(str(getattr(node, "node_type", "")) for node in repo_nodes)
        # 1. Fetch all edges for the repo
        repo_edges = await self._graph_store.list_edges_by_scope(repo_id=str(repo_id))
        
        # 2. Build map of nodes and containment map (parent map)
        node_id_to_node = {str(getattr(node, "id")): node for node in repo_nodes}
        parent_map: dict[str, str] = {} # child_id -> parent_id
        for edge in repo_edges:
            if edge.relation == "contains":
                parent_map[str(edge.target_id)] = str(edge.source_id)
        
        # 3. Identify dependency relations
        dependency_relations = {"depends_on", "uses_external_service", "calls", "imports"}
        
        # 4. Find all dependency edges and group by high-level owner
        # owner_id -> set of target info
        owner_to_deps: dict[str, set[tuple[str, str, str]]] = {} 
        
        high_level_types = {"service", "repository", "module", "controller"}
        
        for edge in repo_edges:
            if edge.relation not in dependency_relations:
                continue
            
            source_id = str(edge.source_id)
            target_id = str(edge.target_id)
            
            # Find high-level owner for the source node
            curr_id = source_id
            owner_node = None
            
            # Search upwards for a high-level owner
            visited = {curr_id}
            while curr_id in node_id_to_node:
                node = node_id_to_node[curr_id]
                if str(getattr(node, "node_type", "")) in high_level_types:
                    owner_node = node
                    break
                
                parent_id = parent_map.get(curr_id)
                if not parent_id or parent_id in visited:
                    break
                curr_id = parent_id
                visited.add(curr_id)
            
            if not owner_node:
                continue
                
            # Get target info
            target_node = node_id_to_node.get(target_id)
            if not target_node:
                continue
            
            owner_id = str(owner_node.id)
            if owner_id not in owner_to_deps:
                owner_to_deps[owner_id] = set()
            
            owner_to_deps[owner_id].add((
                target_id,
                str(getattr(target_node, "name", "")),
                str(getattr(target_node, "node_type", "")),
            ))

        # 5. Format the results
        dependencies: list[dict[str, Any]] = []
        for owner_id, targets in owner_to_deps.items():
            owner_node = node_id_to_node[owner_id]
            depends_on_items: list[dict[str, str]] = [
                {"id": tid, "name": tname, "node_type": ttype}
                for tid, tname, ttype in targets
            ]
            dependencies.append({
                "service": str(getattr(owner_node, "name", "")),
                "source_type": str(getattr(owner_node, "node_type", "")),
                "depends_on": sorted(depends_on_items, key=lambda item: item["name"]),
            })
        dependencies.sort(key=lambda item: str(item["service"]))

        return {
            "repository": repository_payload,
            "graph_available": True,
            "active_branch": effective_branch,
            "branch_state": branch_state,
            "branch_links": branch_links["links"],
            "last_sync": self._repository_last_sync(repository),
            "node_count": len(repo_nodes),
            "counts_by_type": dict(counts),
            "routes": self._serialize_repo_graph_nodes(
                repo_nodes, 
                allowed_types={"route", "api_endpoint", "websocket_endpoint"}, 
                limit=50
            ),
            "todos": self._serialize_repo_graph_nodes(
                repo_nodes, 
                allowed_types={"todo"}, 
                limit=50
            ),
            "external_services": self._serialize_repo_graph_nodes(
                repo_nodes, 
                allowed_types={"external_service_api", "external_service"}, 
                limit=50
            ),
            "dependencies": dependencies,
        }

    async def get_repository_graph_map(
        self,
        *,
        repo_id: uuid.UUID,
        branch: str | None = None,
        node_types: list[str] | None = None,
        limit: int | None = 1000,
    ) -> RepositoryGraphMapPayload:
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        # Default to the repo's default_branch when no branch is specified
        effective_branch = branch or getattr(repository, "default_branch", None) or None

        repository_payload = self.serialize_repository(repository)
        branch_state = self._repository_branch_state_payload(
            repository, effective_branch
        )
        branch_links = await self.list_repository_branch_links(
            repo_id=repo_id, branch=effective_branch
        )
        if self._graph_store is None:
            return {
                "repository": repository_payload,
                "graph_available": False,
                "branch": effective_branch,
                "branch_state": branch_state,
                "branch_links": branch_links["links"],
                "nodes": [],
                "edges": [],
                "summary": {
                    "node_count": 0,
                    "edge_count": 0,
                    "counts_by_type": {},
                    "counts_by_relation": {},
                },
            }

        _, repo_nodes, repo_edges = await self._graph_tools.list_repo_graph(
            repo_id=str(repo_id),
            repo_name=getattr(repository, "repo_name", None),
            repo_path=self._repository_root_path(repository),
            branch=effective_branch,
            node_types=node_types,
        )

        total_nodes = len(repo_nodes)
        total_edges = len(repo_edges)

        # If too many nodes, we limit the return set to prevent browser freeze
        # We prioritize nodes by their 'importance' (node_type)
        if limit and len(repo_nodes) > limit:
            # Simple heuristic: prioritize non-file nodes first (higher level abstraction)
            type_priority = {
                "repository": 0,
                "service": 1,
                "module": 2,
                "controller": 3,
                "route": 4,
                "api_endpoint": 5,
                "websocket_endpoint": 6,
                "mq_topic": 7,
                "external_service_api": 8,
                "workflow": 9,
                "folder": 10,
                "file": 11,
                "todo": 12,
                "class": 20,
                "interface": 21,
                "abstract_class": 22,
                "function": 23,
            }
            repo_nodes.sort(key=lambda n: type_priority.get(getattr(n, "node_type", ""), 15))
            repo_nodes = repo_nodes[:limit]
            
            # Filter edges to only those connecting remaining nodes
            node_ids = {n.id for n in repo_nodes}
            repo_edges = [e for e in repo_edges if e.source_id in node_ids and e.target_id in node_ids]
        node_counts = Counter(
            str(getattr(node, "node_type", "")) for node in repo_nodes
        )
        relation_counts = Counter(
            str(getattr(edge, "relation", "")) for edge in repo_edges
        )
        return {
            "repository": repository_payload,
            "graph_available": bool(repo_nodes),
            "branch": effective_branch,
            "branch_state": branch_state,
            "branch_links": branch_links["links"],
            "nodes": [self._serialize_graph_node(node) for node in repo_nodes],
            "edges": [self._serialize_graph_edge(edge) for edge in repo_edges],
            "summary": {
                "node_count": total_nodes,
                "edge_count": total_edges,
                "returned_node_count": len(repo_nodes),
                "returned_edge_count": len(repo_edges),
                "counts_by_type": dict(node_counts),
                "counts_by_relation": dict(relation_counts),
            },
        }

    async def get_repository_node_neighborhood(
        self,
        *,
        repo_id: uuid.UUID,
        node_id: uuid.UUID,
        depth: int = 4,
        limit: int = 200,
    ) -> RepositoryGraphMapPayload:
        """Fetch a subgraph around a specific node with limited depth/count."""
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        if self._graph_store is None:
            raise RuntimeError("Graph store is not configured")

        repo_nodes, repo_edges = await self._graph_store.get_neighborhood(
            node_id=node_id,
            max_depth=depth,
            max_nodes=limit,
        )

        repository_payload = self.serialize_repository(repository)
        
        # Calculate summary
        node_counts = Counter(
            str(getattr(node, "node_type", "")) for node in repo_nodes
        )
        relation_counts = Counter(
            str(getattr(edge, "relation", "")) for edge in repo_edges
        )

        return {
            "repository": repository_payload,
            "graph_available": bool(repo_nodes),
            "branch": getattr(repo_nodes[0], "branch", None) if repo_nodes else None,
            "branch_state": None,
            "branch_links": [],
            "nodes": [self._serialize_graph_node(node) for node in repo_nodes],
            "edges": [self._serialize_graph_edge(edge) for edge in repo_edges],
            "summary": {
                "node_count": len(repo_nodes),
                "edge_count": len(repo_edges),
                "returned_node_count": len(repo_nodes),
                "returned_edge_count": len(repo_edges),
                "counts_by_type": dict(node_counts),
                "counts_by_relation": dict(relation_counts),
            },
        }

    async def prune_repository_stale_data(self, repo_id: uuid.UUID) -> dict[str, Any]:
        """Delete graph data for branches that are no longer tracked."""
        if self._graph_store is None:
            return {"deleted": 0}
        
        repository = await self._store.get_repository_by_id(repo_id)
        if not repository:
            return {"deleted": 0}

        tracked = set(getattr(repository, "tracked_branches", []) or [])
        if not tracked:
            return {"deleted": 0}

        repo_id_str = str(repo_id)
        branches_in_graph = await self._graph_store.list_repo_branches(repo_id_str)
        
        deleted_total = 0
        for branch in branches_in_graph:
            if branch not in tracked:
                logger.info(f"Pruning stale branch data: {repo_id_str}/{branch}")
                deleted_total += await self._graph_store.delete_nodes_by_scope(
                    repo_id=repo_id_str, branch=branch
                )
        
        return {"deleted": deleted_total}

    async def search_repository_graph(
        self,
        *,
        repo_id: uuid.UUID,
        query: str,
        branch: str | None = None,
        node_types: list[str] | None = None,
        languages: list[str] | None = None,
        last_states: list[str] | None = None,
        limit: int = 10,
    ) -> RepositoryGraphSearchPayload:
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")
        if self._graph_store is None:
            raise RuntimeError("Graph sync store is not configured")

        result = await self._graph_tools.minder_search_graph(
            query,
            repo_id=str(repo_id),
            repo_name=getattr(repository, "repo_name", None),
            repo_path=self._repository_root_path(repository),
            branch=branch,
            node_types=node_types,
            languages=languages,
            last_states=last_states,
            limit=limit,
            include_linked_repos=True,
        )
        searched_scopes = result.get("searched_scopes", [])
        active_branch = branch
        if searched_scopes:
            active_branch = searched_scopes[0].get("branch")
        return {
            "repository": self.serialize_repository(repository),
            "active_branch": active_branch,
            "query": query,
            "filters": result["filters"],
            "scope_count": int(result.get("scope_count", len(searched_scopes))),
            "searched_scopes": searched_scopes,
            "count": result["count"],
            "results": result["results"],
        }

    async def get_repository_graph_impact(
        self,
        *,
        repo_id: uuid.UUID,
        target: str,
        branch: str | None = None,
        depth: int = 2,
        limit: int = 25,
    ) -> RepositoryGraphImpactPayload:
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")
        if self._graph_store is None:
            raise RuntimeError("Graph sync store is not configured")

        result = await self._graph_tools.minder_find_impact(
            target,
            repo_id=str(repo_id),
            repo_name=getattr(repository, "repo_name", None),
            repo_path=self._repository_root_path(repository),
            branch=branch,
            depth=depth,
            limit=limit,
            include_linked_repos=True,
        )
        searched_scopes = result.get("searched_scopes", [])
        active_branch = branch
        if searched_scopes:
            active_branch = searched_scopes[0].get("branch")
        return {
            "repository": self.serialize_repository(repository),
            "active_branch": active_branch,
            "target": target,
            "searched_scopes": searched_scopes,
            "matches": result["matches"],
            "impacted": result["impacted"],
            "summary": result["summary"],
        }

    # ------------------------------------------------------------------
    # Branch management
    # ------------------------------------------------------------------

    async def list_repository_branches(
        self,
        *,
        repo_id: uuid.UUID,
    ) -> RepositoryBranchListPayload:
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        tracked_branches: list[RepositoryBranchPayload] = []
        for branch_name in self._repository_branch_names(repository):
            branch_state = self._repository_branch_state_payload(
                repository, branch_name
            )
            if branch_state is not None:
                tracked_branches.append(branch_state)

        return {
            "repo_id": str(repo_id),
            "default_branch": getattr(repository, "default_branch", None),
            "tracked_branches": tracked_branches,
        }

    async def add_repository_branch(
        self,
        *,
        repo_id: uuid.UUID,
        branch: str,
    ) -> "RepositoryBranchListPayload":
        branch = branch.strip()
        if not branch:
            raise ValueError("Branch name is required")

        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        raw_branches = list(getattr(repository, "tracked_branches", None) or [])
        if branch not in raw_branches:
            raw_branches.append(branch)
            await self._store.update_repository(repo_id, tracked_branches=raw_branches)

        return await self.list_repository_branches(repo_id=repo_id)

    async def remove_repository_branch(
        self,
        *,
        repo_id: uuid.UUID,
        branch: str,
    ) -> "RepositoryBranchListPayload":
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        default_branch = getattr(repository, "default_branch", None)
        if branch == default_branch:
            raise ValueError("Cannot remove the default branch")

        raw_branches = list(getattr(repository, "tracked_branches", None) or [])
        raw_branches = [b for b in raw_branches if b != branch]
        await self._store.update_repository(repo_id, tracked_branches=raw_branches)
        return await self.list_repository_branches(repo_id=repo_id)

    async def list_repository_branch_links(
        self,
        *,
        repo_id: uuid.UUID,
        branch: str | None = None,
    ) -> RepositoryBranchLinkListPayload:
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        repo_id_str = str(repo_id)
        repositories = await self._store.list_repositories()
        links: list[RepositoryBranchLinkPayload] = []
        for candidate in repositories:
            for link in self._repository_branch_links(candidate):
                source_repo_id = str(link.get("source_repo_id", "") or "")
                target_repo_id = str(link.get("target_repo_id", "") or "")
                if repo_id_str not in {source_repo_id, target_repo_id}:
                    continue
                if branch:
                    if (
                        source_repo_id == repo_id_str
                        and str(link.get("source_branch", "") or "") != branch
                    ):
                        continue
                    if (
                        target_repo_id == repo_id_str
                        and str(link.get("target_branch", "") or "") != branch
                    ):
                        continue
                links.append(self._serialize_branch_link(link))

        links.sort(
            key=lambda item: (
                0 if item["source_repo_id"] == repo_id_str else 1,
                item["source_branch"],
                item["target_repo_name"],
                item["target_branch"],
                item["relation"],
            )
        )
        return {
            "repo_id": repo_id_str,
            "branch": branch,
            "links": links,
        }

    async def upsert_repository_branch_link(
        self,
        *,
        repo_id: uuid.UUID,
        source_branch: str,
        target_repo_id: str | None = None,
        target_repo_name: str | None = None,
        target_repo_url: str | None = None,
        target_branch: str,
        relation: str = "depends_on",
        direction: str = "outbound",
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> RepositoryBranchLinkListPayload:
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        normalized_source_branch = source_branch.strip()
        normalized_target_branch = target_branch.strip()
        if not normalized_source_branch:
            raise ValueError("Source branch is required")
        if not normalized_target_branch:
            raise ValueError("Target branch is required")
        if not (target_repo_id or target_repo_name or target_repo_url):
            raise ValueError("Target repository is required")

        repositories = await self._store.list_repositories()
        new_links = self._build_branch_links(
            repository=repository,
            repositories=repositories,
            source_branch=normalized_source_branch,
            accepted_at=datetime.now(UTC).isoformat(),
            source="admin-console",
            specs=[
                {
                    "source_branch": normalized_source_branch,
                    "target_repo_id": target_repo_id,
                    "target_repo_name": target_repo_name,
                    "target_repo_url": target_repo_url,
                    "target_branch": normalized_target_branch,
                    "relation": relation,
                    "direction": direction,
                    "confidence": confidence,
                    "metadata": metadata or {},
                }
            ],
        )
        relationships = dict(getattr(repository, "relationships", {}) or {})
        relationships["cross_repo_branches"] = self._merge_branch_links(
            self._repository_branch_links(repository),
            new_links,
        )
        tracked_branches = list(getattr(repository, "tracked_branches", None) or [])
        if (
            normalized_source_branch != getattr(repository, "default_branch", None)
            and normalized_source_branch not in tracked_branches
        ):
            tracked_branches.append(normalized_source_branch)
        await self._store.update_repository(
            repo_id,
            relationships=relationships,
            tracked_branches=tracked_branches,
        )
        return await self.list_repository_branch_links(
            repo_id=repo_id, branch=normalized_source_branch
        )

    async def delete_repository_branch_link(
        self,
        *,
        repo_id: uuid.UUID,
        link_id: str,
        branch: str | None = None,
    ) -> RepositoryBranchLinkListPayload:
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        existing_links = self._repository_branch_links(repository)
        filtered_links = [
            link for link in existing_links if str(link.get("id", "") or "") != link_id
        ]
        if len(filtered_links) == len(existing_links):
            raise LookupError("Repository branch link not found")

        relationships = dict(getattr(repository, "relationships", {}) or {})
        relationships["cross_repo_branches"] = filtered_links
        await self._store.update_repository(repo_id, relationships=relationships)
        return await self.list_repository_branch_links(repo_id=repo_id, branch=branch)

    async def list_repository_landscape(self) -> RepositoryLandscapePayload:
        repositories = await self._store.list_repositories()
        repository_payloads = [
            self.serialize_repository(repository) for repository in repositories
        ]
        nodes_by_id: dict[str, Any] = {}
        edges: list[Any] = []

        for repository in repositories:
            repo_id_str = str(getattr(repository, "id"))
            repo_name = str(getattr(repository, "repo_name", "") or "")
            remote_url = _normalize_repository_remote(
                getattr(repository, "repo_url", None)
            )
            default_branch = str(getattr(repository, "default_branch", "") or "")
            for branch_name in self._repository_branch_names(repository):
                branch_state = self._repository_branch_state_payload(
                    repository, branch_name
                )
                node_id = self._landscape_node_id(repo_id_str, branch_name)
                nodes_by_id[node_id] = {
                    "id": node_id,
                    "repo_id": repo_id_str,
                    "repo_name": repo_name,
                    "branch": branch_name,
                    "remote_url": remote_url,
                    "is_default": branch_name == default_branch,
                    "last_synced": (
                        branch_state["last_synced"]
                        if branch_state is not None
                        else None
                    ),
                }

        for repository in repositories:
            for link in self._repository_branch_links(repository):
                source_repo_id = str(link.get("source_repo_id", "") or "")
                source_branch = str(link.get("source_branch", "") or "")
                target_repo_id = str(link.get("target_repo_id", "") or "")
                target_repo_name = str(link.get("target_repo_name", "") or "")
                target_repo_url = _normalize_repository_remote(
                    link.get("target_repo_url")
                )
                target_branch = str(link.get("target_branch", "") or "")
                if not source_repo_id or not source_branch or not target_branch:
                    continue

                source_node_id = self._landscape_node_id(source_repo_id, source_branch)
                if source_node_id not in nodes_by_id:
                    continue

                target_node_repo_id = target_repo_id or self._external_repo_key(
                    target_repo_name, target_repo_url
                )
                target_node_id = self._landscape_node_id(
                    target_node_repo_id, target_branch
                )
                if target_node_id not in nodes_by_id:
                    nodes_by_id[target_node_id] = {
                        "id": target_node_id,
                        "repo_id": target_node_repo_id,
                        "repo_name": target_repo_name or target_node_repo_id,
                        "branch": target_branch,
                        "remote_url": target_repo_url,
                        "is_default": False,
                        "last_synced": None,
                    }

                edges.append(
                    {
                        "id": str(link.get("id", "") or ""),
                        "source_id": source_node_id,
                        "target_id": target_node_id,
                        "relation": str(
                            link.get("relation", "depends_on") or "depends_on"
                        ),
                        "direction": str(
                            link.get("direction", "outbound") or "outbound"
                        ),
                        "confidence": float(link.get("confidence", 1.0) or 1.0),
                    }
                )

        return {
            "repositories": repository_payloads,
            "nodes": sorted(
                nodes_by_id.values(),
                key=lambda item: (item["repo_name"], item["branch"]),
            ),
            "edges": sorted(
                edges,
                key=lambda item: (
                    item["relation"],
                    item["source_id"],
                    item["target_id"],
                ),
            ),
            "summary": {
                "repo_count": len(repository_payloads),
                "branch_count": len(nodes_by_id),
                "link_count": len(edges),
            },
        }

    @staticmethod
    def _repository_last_sync(repository: Any) -> dict[str, Any] | None:
        relationships = dict(getattr(repository, "relationships", {}) or {})
        graph_sync = relationships.get("graph_sync")
        if not isinstance(graph_sync, dict):
            return None
        last_sync = graph_sync.get("last_sync")
        if isinstance(last_sync, dict):
            return last_sync
        return graph_sync

    async def _find_repository_for_client_sync(
        self,
        *,
        repo_name: str,
        repo_path: str,
        repo_url: str | None,
    ) -> Any | None:
        normalized_name = repo_name.strip()
        normalized_url = _normalize_repository_remote(repo_url)

        repositories = await self._store.list_repositories()
        for repository in repositories:
            repository_name = str(getattr(repository, "repo_name", "") or "").strip()
            repository_url = _normalize_repository_remote(
                getattr(repository, "repo_url", None)
            )
            if normalized_url and repository_url and repository_url == normalized_url:
                return repository
            if (
                repository_name
                and repository_name == normalized_name
                and not repository_url
            ):
                return repository
        return None

    @staticmethod
    def _repository_root_path(repository: Any) -> str | None:
        state_path = str(getattr(repository, "state_path", "") or "")
        if not state_path:
            return None
        state_root = Path(state_path)
        if state_root.name == ".minder":
            return str(state_root.parent)
        return str(state_root)

    async def _repository_graph_nodes(
        self, repository: Any, *, branch: str | None = None
    ) -> list[Any]:
        _, repo_nodes = await self._graph_tools.list_repo_nodes(
            repo_id=str(getattr(repository, "id")),
            repo_name=str(getattr(repository, "repo_name", "") or ""),
            repo_path=self._repository_root_path(repository),
            branch=branch,
        )
        return repo_nodes

    @staticmethod
    def _serialize_graph_node(node: Any) -> RepositoryGraphNodePayload:
        metadata = dict(node.extra_metadata or {})
        return {
            "id": str(getattr(node, "id")),
            "node_type": str(getattr(node, "node_type", "")),
            "name": str(getattr(node, "name", "")),
            "metadata": metadata,
        }

    @staticmethod
    def _serialize_graph_edge(edge: Any) -> RepositoryGraphEdgePayload:
        return {
            "id": str(getattr(edge, "id")),
            "source_id": str(getattr(edge, "source_id")),
            "target_id": str(getattr(edge, "target_id")),
            "relation": str(getattr(edge, "relation", "")),
            "weight": float(getattr(edge, "weight", 1.0) or 1.0),
        }

    def _serialize_repo_graph_nodes(
        self,
        nodes: list[Any],
        *,
        allowed_types: set[str],
        limit: int,
    ) -> list[RepositoryGraphNodePayload]:
        filtered = [
            node
            for node in nodes
            if str(getattr(node, "node_type", "")) in allowed_types
        ]
        filtered.sort(
            key=lambda node: (
                str(getattr(node, "node_type", "")),
                str((node.extra_metadata or {}).get("path", "")),
                str(getattr(node, "name", "")),
            )
        )
        return [self._serialize_graph_node(node) for node in filtered[:limit]]

    @staticmethod
    def _repository_branch_names(repository: Any) -> list[str]:
        ordered: list[str] = []
        default_branch = str(getattr(repository, "default_branch", "") or "").strip()
        if default_branch:
            ordered.append(default_branch)
        for branch_name in list(getattr(repository, "tracked_branches", None) or []):
            normalized = str(branch_name).strip()
            if normalized and normalized not in ordered:
                ordered.append(normalized)
        return ordered

    @staticmethod
    def _repository_branch_state_payload(
        repository: Any,
        branch: str | None,
    ) -> RepositoryBranchPayload | None:
        normalized_branch = str(branch or "").strip()
        if not normalized_branch:
            return None
        relationships = dict(getattr(repository, "relationships", {}) or {})
        graph_sync = dict(relationships.get("graph_sync", {}) or {})
        branch_registry = dict(graph_sync.get("branches", {}) or {})
        branch_state = dict(branch_registry.get(normalized_branch, {}) or {})
        return {
            "branch": normalized_branch,
            "is_default": normalized_branch
            == getattr(repository, "default_branch", None),
            "last_synced": str(branch_state.get("accepted_at", "") or "") or None,
            "payload_version": str(branch_state.get("payload_version", "") or "")
            or None,
            "source": str(branch_state.get("source", "") or "") or None,
            "node_count": int(branch_state.get("nodes_upserted", 0) or 0),
            "edge_count": int(branch_state.get("edges_upserted", 0) or 0),
            "deleted_nodes": int(branch_state.get("deleted_nodes", 0) or 0),
            "repo_path": str(branch_state.get("repo_path", "") or "") or None,
            "diff_base": str(branch_state.get("diff_base", "") or "") or None,
        }

    @staticmethod
    def _repository_branch_links(repository: Any) -> list[dict[str, Any]]:
        relationships = dict(getattr(repository, "relationships", {}) or {})
        raw_links = relationships.get("cross_repo_branches", [])
        if not isinstance(raw_links, list):
            return []
        return [dict(link) for link in raw_links if isinstance(link, dict)]

    def _build_branch_links(
        self,
        *,
        repository: Any,
        repositories: list[Any],
        source_branch: str | None,
        accepted_at: str,
        source: str,
        specs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        source_repo_id = str(getattr(repository, "id"))
        source_repo_name = str(getattr(repository, "repo_name", "") or "")
        source_repo_url = _normalize_repository_remote(
            getattr(repository, "repo_url", None)
        )
        fallback_source_branch = str(
            source_branch or getattr(repository, "default_branch", None) or ""
        ).strip()
        built_links: list[dict[str, Any]] = []

        for spec in specs:
            normalized_source_branch = str(
                spec.get("source_branch") or fallback_source_branch
            ).strip()
            target_branch = str(spec.get("target_branch", "") or "").strip()
            if not normalized_source_branch or not target_branch:
                continue

            target_repository = self._resolve_repository_reference(
                repositories=repositories,
                target_repo_id=spec.get("target_repo_id"),
                target_repo_name=spec.get("target_repo_name"),
                target_repo_url=spec.get("target_repo_url"),
            )
            target_repo_id = (
                str(getattr(target_repository, "id"))
                if target_repository is not None
                else None
            )
            target_repo_name = (
                str(getattr(target_repository, "repo_name", "") or "")
                if target_repository is not None
                else str(spec.get("target_repo_name", "") or "").strip()
            )
            target_repo_url = (
                _normalize_repository_remote(
                    getattr(target_repository, "repo_url", None)
                )
                if target_repository is not None
                else _normalize_repository_remote(spec.get("target_repo_url"))
            )
            target_key = target_repo_id or target_repo_url or target_repo_name
            if not target_key:
                continue
            relation = (
                str(spec.get("relation", "depends_on") or "depends_on").strip()
                or "depends_on"
            )
            direction = (
                str(spec.get("direction", "outbound") or "outbound").strip()
                or "outbound"
            )
            link_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{source_repo_id}:{normalized_source_branch}:{relation}:{target_key}:{target_branch}",
                )
            )
            built_links.append(
                {
                    "id": link_id,
                    "source_repo_id": source_repo_id,
                    "source_repo_name": source_repo_name,
                    "source_repo_url": source_repo_url,
                    "source_branch": normalized_source_branch,
                    "target_repo_id": target_repo_id,
                    "target_repo_name": target_repo_name,
                    "target_repo_url": target_repo_url,
                    "target_branch": target_branch,
                    "relation": relation,
                    "direction": direction,
                    "confidence": float(spec.get("confidence", 1.0) or 1.0),
                    "last_seen_at": accepted_at,
                    "source": source,
                    "metadata": dict(spec.get("metadata", {}) or {}),
                }
            )

        return built_links

    @staticmethod
    def _merge_branch_links(
        existing_links: list[dict[str, Any]],
        new_links: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged = {
            str(link.get("id", "") or ""): dict(link)
            for link in existing_links
            if link.get("id")
        }
        for link in new_links:
            link_id = str(link.get("id", "") or "")
            if not link_id:
                continue
            merged[link_id] = {**dict(merged.get(link_id, {})), **dict(link)}
        return list(merged.values())

    @staticmethod
    def _serialize_branch_link(link: dict[str, Any]) -> RepositoryBranchLinkPayload:
        return {
            "id": str(link.get("id", "") or ""),
            "source_repo_id": str(link.get("source_repo_id", "") or ""),
            "source_repo_name": str(link.get("source_repo_name", "") or ""),
            "source_repo_url": _normalize_repository_remote(
                link.get("source_repo_url")
            ),
            "source_branch": str(link.get("source_branch", "") or ""),
            "target_repo_id": str(link.get("target_repo_id", "") or "") or None,
            "target_repo_name": str(link.get("target_repo_name", "") or ""),
            "target_repo_url": _normalize_repository_remote(
                link.get("target_repo_url")
            ),
            "target_branch": str(link.get("target_branch", "") or ""),
            "relation": str(link.get("relation", "depends_on") or "depends_on"),
            "direction": str(link.get("direction", "outbound") or "outbound"),
            "confidence": float(link.get("confidence", 1.0) or 1.0),
            "last_seen_at": str(link.get("last_seen_at", "") or "") or None,
            "source": str(link.get("source", "") or "") or None,
            "metadata": dict(link.get("metadata", {}) or {}),
        }

    @staticmethod
    def _resolve_repository_reference(
        *,
        repositories: list[Any],
        target_repo_id: Any,
        target_repo_name: Any,
        target_repo_url: Any,
    ) -> Any | None:
        normalized_target_id = str(target_repo_id or "").strip()
        normalized_target_name = str(target_repo_name or "").strip()
        normalized_target_url = _normalize_repository_remote(target_repo_url)
        for repository in repositories:
            if (
                normalized_target_id
                and str(getattr(repository, "id")) == normalized_target_id
            ):
                return repository
            if (
                normalized_target_url
                and _normalize_repository_remote(getattr(repository, "repo_url", None))
                == normalized_target_url
            ):
                return repository
            if (
                normalized_target_name
                and str(getattr(repository, "repo_name", "") or "")
                == normalized_target_name
            ):
                return repository
        return None

    @staticmethod
    def _landscape_node_id(repo_id: str, branch: str) -> str:
        return f"{repo_id}:{branch}"

    @staticmethod
    def _external_repo_key(repo_name: str, repo_url: str | None) -> str:
        normalized_name = repo_name.strip() or "external-repo"
        normalized_url = _normalize_repository_remote(repo_url)
        return f"external:{normalized_url or normalized_name}"


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


def _repo_name_from_remote(repo_url: str | None) -> str | None:
    normalized_url = _normalize_repository_remote(repo_url)
    if not normalized_url:
        return None
    _, _, path = normalized_url.partition(":")
    repo_name = path.rsplit("/", 1)[-1].removesuffix(".git").strip()
    return repo_name or None
