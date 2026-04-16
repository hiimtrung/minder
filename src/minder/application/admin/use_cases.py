from __future__ import annotations

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
    RepositoryDetailPayload,
    RepositoryGraphEdgePayload,
    RepositoryGraphImpactPayload,
    RepositoryGraphMapPayload,
    RepositoryGraphNodePayload,
    RepositoryGraphSearchPayload,
    RepositoryGraphSummaryPayload,
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
        self._graph_tools = GraphTools(graph_store)

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
        user = await self._auth_service.authenticate_username_password(username, password)
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
        return {"clients": [self.serialize_client(client) for client in await self._store.list_clients()]}

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
        await self._auth_service.revoke_client_api_keys(client_id, actor_user_id=actor_user_id)
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
            "templates": self.onboarding_templates(client, public_base_url=public_base_url),
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
            "templates": self.onboarding_templates(client, public_base_url=public_base_url),
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
        serialized = [await self.serialize_audit_event_enriched(event) for event in events]
        return {"events": serialized, "total": total, "limit": limit, "offset": offset}

    async def get_recent_client_activity(
        self,
        client_id: uuid.UUID,
        *,
        limit: int = 8,
    ) -> list[ActivityEventPayload]:
        events = await self._store.list_audit_logs()
        filtered = [event for event in events if str(getattr(event, "resource_id", "")) == str(client_id)]
        filtered.sort(key=lambda event: getattr(event, "created_at", None) or "", reverse=True)
        return [
            {
                "event_type": str(getattr(event, "event_type", "")),
                "created_at": getattr(event, "created_at").isoformat() if getattr(event, "created_at", None) else "unknown time",
            }
            for event in filtered[:limit]
        ]

    async def list_repo_scope_candidates(self) -> list[str]:
        candidates = ["*", "/workspace/repo", "/workspace/docs"]
        clients = await self._store.list_clients()
        for client in clients:
            candidates.extend(list(getattr(client, "repo_scopes", [])))
        return self.dedupe_preserve_order(candidates)

    def onboarding_templates(self, client: Any, *, public_base_url: str | None = None) -> dict[str, str]:
        base_url = public_base_url.rstrip("/") if public_base_url else f"http://localhost:{self._config.server.port}"
        return {
            "codex": (
                '[mcp_servers.minder]\n'
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
                    base["actor_name"] = getattr(actor, "display_name", None) or getattr(actor, "username", None)
            elif event.actor_type == "client":
                actor_client = await self._store.get_client_by_id(uuid.UUID(event.actor_id))
                if actor_client:
                    base["actor_name"] = getattr(actor_client, "name", None)
        except Exception:
            pass

        # Resolve resource name
        try:
            if event.resource_type == "client":
                resource_client = await self._store.get_client_by_id(uuid.UUID(event.resource_id))
                if resource_client:
                    base["resource_name"] = getattr(resource_client, "name", None)
            elif event.resource_type == "user":
                resource_user = await self._store.get_user_by_id(uuid.UUID(event.resource_id))
                if resource_user:
                    base["resource_name"] = getattr(resource_user, "display_name", None) or getattr(resource_user, "username", None)
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
            "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
        }

    # ------------------------------------------------------------------
    # Workflow management
    # ------------------------------------------------------------------

    async def list_workflows(self) -> WorkflowListPayload:
        workflows = await self._store.list_workflows()
        return {"workflows": [self.serialize_workflow(w) for w in workflows]}

    async def get_workflow_detail(self, workflow_id: uuid.UUID) -> WorkflowDetailPayload:
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
            "created_at": workflow.created_at.isoformat() if getattr(workflow, "created_at", None) else None,
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

    async def get_repository_detail(self, repo_id: uuid.UUID) -> RepositoryDetailPayload:
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
            raise ValueError("Repository remote SSH URL is required for repository resolution")

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
            existing_remote = _normalize_repository_remote(getattr(repository, "repo_url", None))
            if existing_remote != normalized_url:
                updates["repo_url"] = normalized_url
            if str(getattr(repository, "state_path", "") or "") != state_path:
                updates["state_path"] = state_path
            if normalized_branch and str(getattr(repository, "default_branch", "") or "") != normalized_branch:
                updates["default_branch"] = normalized_branch
            if updates:
                repository = await self._store.update_repository(repository.id, **updates) or repository

        return {
            "repository": self.serialize_repository(repository),
            "created": created,
        }

    @staticmethod
    def serialize_repository(repo: Any, state: Any = None) -> RepositoryPayload:
        raw_branches = getattr(repo, "tracked_branches", None)
        tracked: list[str] = list(raw_branches) if isinstance(raw_branches, list) else []
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
            "created_at": repo.created_at.isoformat() if getattr(repo, "created_at", None) else None,
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

        repo_name = getattr(repository, "repo_name", getattr(repository, "name", str(repo_id)))
        repo_remote = _normalize_repository_remote(getattr(repository, "repo_url", None))
        branch = payload.branch or getattr(repository, "default_branch", None)
        accepted_at = datetime.now(UTC).isoformat()
        node_ids: dict[tuple[str, str], uuid.UUID] = {}
        deleted_nodes = 0
        nodes_upserted = 0
        edges_upserted = 0

        # --- Scoped deletion: prune stale nodes for changed/deleted files ---
        changed_files = payload.sync_metadata.get("changed_files", [])
        paths_to_prune: set[str] = set(payload.deleted_files)
        if isinstance(changed_files, list):
            paths_to_prune.update(str(p) for p in changed_files if isinstance(p, str) and p.strip())
        paths_to_prune.update(
            str(node.metadata.get("path"))
            for node in payload.nodes
            if isinstance(node.metadata.get("path"), str) and str(node.metadata.get("path")).strip()
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
                    metadata = dict(getattr(graph_node, "node_metadata", {}) or {})
                    if metadata.get("repo_id") != str(repo_id):
                        continue
                    if branch is not None and metadata.get("branch") not in {None, branch}:
                        continue
                    if str(metadata.get("path", "") or "") not in paths_to_prune:
                        continue
                    await self._graph_store.delete_node(graph_node.id)
                    deleted_nodes += 1

        # --- Upsert nodes with proper repo/branch scope (v2) ---
        _branch = branch or ""
        _repo_id_str = str(repo_id)
        _common_meta = {
            "repo_id": _repo_id_str,
            "repository_name": repo_name,
            "repository_remote": repo_remote,
            "source": payload.source,
            "payload_version": payload.payload_version,
            "branch": _branch,
            "repo_path": payload.repo_path,
            "diff_base": payload.diff_base,
            **payload.sync_metadata,
        }

        for node in payload.nodes:
            persisted = await self._graph_store.upsert_node(
                node.node_type,
                node.name,
                metadata={**_common_meta, **node.metadata},
                repo_id=_repo_id_str,
                branch=_branch,
            )
            node_ids[(node.node_type, node.name)] = persisted.id
            nodes_upserted += 1

        _edge_common_meta = {
            "repo_id": _repo_id_str,
            "repository_name": repo_name,
            "repository_remote": repo_remote,
            "source": payload.source,
            "payload_version": payload.payload_version,
            "branch": _branch,
            "repo_path": payload.repo_path,
        }

        for edge in payload.edges:
            source_key = (edge.source.node_type, edge.source.name)
            target_key = (edge.target.node_type, edge.target.name)

            if source_key not in node_ids:
                source_node = await self._graph_store.upsert_node(
                    edge.source.node_type,
                    edge.source.name,
                    metadata=_edge_common_meta,
                    repo_id=_repo_id_str,
                    branch=_branch,
                )
                node_ids[source_key] = source_node.id
                nodes_upserted += 1

            if target_key not in node_ids:
                target_node = await self._graph_store.upsert_node(
                    edge.target.node_type,
                    edge.target.name,
                    metadata=_edge_common_meta,
                    repo_id=_repo_id_str,
                    branch=_branch,
                )
                node_ids[target_key] = target_node.id
                nodes_upserted += 1

            await self._graph_store.upsert_edge(
                source_id=node_ids[source_key],
                target_id=node_ids[target_key],
                relation=edge.relation,
                weight=edge.weight,
                repo_id=_repo_id_str,
            )
            edges_upserted += 1

        # --- Update repository: tracked_branches + graph_sync metadata ---
        relationships = dict(getattr(repository, "relationships", {}) or {})
        relationships["graph_sync"] = {
            "payload_version": payload.payload_version,
            "source": payload.source,
            "branch": branch,
            "repo_path": payload.repo_path,
            "repo_remote": repo_remote,
            "diff_base": payload.diff_base,
            "deleted_files": payload.deleted_files,
            "deleted_nodes": deleted_nodes,
            "nodes_upserted": nodes_upserted,
            "edges_upserted": edges_upserted,
            "accepted_at": accepted_at,
        }

        # Auto-register branch in tracked_branches on first sync
        if branch:
            raw_branches = list(getattr(repository, "tracked_branches", None) or [])
            if branch not in raw_branches:
                raw_branches.append(branch)
            await self._store.update_repository(
                repo_id,
                relationships=relationships,
                tracked_branches=raw_branches,
            )
        else:
            await self._store.update_repository(repo_id, relationships=relationships)

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
        if self._graph_store is None:
            return {
                "repository": repository_payload,
                "graph_available": False,
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
        repo_node_ids = {str(getattr(node, "id")) for node in repo_nodes}
        services = [node for node in repo_nodes if str(getattr(node, "node_type", "")) == "service"]
        dependencies: list[dict[str, Any]] = []
        for service in services:
            neighbors = await self._graph_store.get_neighbors(
                getattr(service, "id"),
                direction="out",
                relation="depends_on",
            )
            targets = [
                {
                    "id": str(getattr(neighbor, "id")),
                    "name": str(getattr(neighbor, "name", "")),
                    "node_type": str(getattr(neighbor, "node_type", "")),
                }
                for neighbor in neighbors
                if str(getattr(neighbor, "id")) in repo_node_ids
            ]
            if targets:
                dependencies.append(
                    {
                        "service": str(getattr(service, "name", "")),
                        "depends_on": sorted(targets, key=lambda item: item["name"]),
                    }
                )

        return {
            "repository": repository_payload,
            "graph_available": True,
            "last_sync": self._repository_last_sync(repository),
            "node_count": len(repo_nodes),
            "counts_by_type": dict(counts),
            "routes": self._serialize_repo_graph_nodes(repo_nodes, allowed_types={"route"}, limit=12),
            "todos": self._serialize_repo_graph_nodes(repo_nodes, allowed_types={"todo"}, limit=12),
            "external_services": self._serialize_repo_graph_nodes(repo_nodes, allowed_types={"external_service_api"}, limit=12),
            "dependencies": dependencies,
        }

    async def get_repository_graph_map(
        self,
        *,
        repo_id: uuid.UUID,
        branch: str | None = None,
    ) -> RepositoryGraphMapPayload:
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        # Default to the repo's default_branch when no branch is specified
        effective_branch = branch or getattr(repository, "default_branch", None) or None

        repository_payload = self.serialize_repository(repository)
        if self._graph_store is None:
            return {
                "repository": repository_payload,
                "graph_available": False,
                "branch": effective_branch,
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
        )
        node_counts = Counter(str(getattr(node, "node_type", "")) for node in repo_nodes)
        relation_counts = Counter(str(getattr(edge, "relation", "")) for edge in repo_edges)
        return {
            "repository": repository_payload,
            "graph_available": bool(repo_nodes),
            "branch": effective_branch,
            "nodes": [self._serialize_graph_node(node) for node in repo_nodes],
            "edges": [self._serialize_graph_edge(edge) for edge in repo_edges],
            "summary": {
                "node_count": len(repo_nodes),
                "edge_count": len(repo_edges),
                "counts_by_type": dict(node_counts),
                "counts_by_relation": dict(relation_counts),
            },
        }

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
        )
        return {
            "repository": self.serialize_repository(repository),
            "query": query,
            "filters": result["filters"],
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
        )
        return {
            "repository": self.serialize_repository(repository),
            "target": target,
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
    ) -> "RepositoryBranchListPayload":
        from minder.application.admin.dto import RepositoryBranchListPayload  # local import avoids circular
        repository = await self._store.get_repository_by_id(repo_id)
        if repository is None:
            raise LookupError("Repository not found")

        default_branch = getattr(repository, "default_branch", None)
        raw_branches = list(getattr(repository, "tracked_branches", None) or [])
        # Ensure default branch is always in the list
        if default_branch and default_branch not in raw_branches:
            raw_branches.insert(0, default_branch)

        relationships = dict(getattr(repository, "relationships", {}) or {})
        graph_sync = relationships.get("graph_sync", {}) or {}
        last_sync_branch = str(graph_sync.get("branch", "") or "")
        last_sync_at = str(graph_sync.get("accepted_at", "") or "")

        branch_payloads = []
        for b in raw_branches:
            branch_payloads.append({
                "branch": b,
                "is_default": b == default_branch,
                "last_synced": last_sync_at if b == last_sync_branch else None,
            })

        return {
            "repo_id": str(repo_id),
            "default_branch": default_branch,
            "tracked_branches": branch_payloads,
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
            repository = await self._store.get_repository_by_id(repo_id) or repository

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

    @staticmethod
    def _repository_last_sync(repository: Any) -> dict[str, Any] | None:
        relationships = dict(getattr(repository, "relationships", {}) or {})
        graph_sync = relationships.get("graph_sync")
        return graph_sync if isinstance(graph_sync, dict) else None

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
            repository_url = _normalize_repository_remote(getattr(repository, "repo_url", None))
            if normalized_url and repository_url and repository_url == normalized_url:
                return repository
            if repository_name and repository_name == normalized_name and not repository_url:
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
        metadata = dict(getattr(node, "node_metadata", {}) or {})
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
            node for node in nodes if str(getattr(node, "node_type", "")) in allowed_types
        ]
        filtered.sort(
            key=lambda node: (
                str(getattr(node, "node_type", "")),
                str(dict(getattr(node, "node_metadata", {}) or {}).get("path", "")),
                str(getattr(node, "name", "")),
            )
        )
        return [self._serialize_graph_node(node) for node in filtered[:limit]]


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
    if raw_url.startswith("ssh://") or raw_url.startswith("http://") or raw_url.startswith("https://"):
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
