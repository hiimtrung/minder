from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from minder.tools.registry import SCOPEABLE_TOOLS
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
    ClientPayload,
    CreateClientPayload,
    CreateUserPayload,
    GraphSyncRequest,
    GraphSyncResultPayload,
    OnboardingPayload,
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

    @staticmethod
    def serialize_repository(repo: Any, state: Any = None) -> RepositoryPayload:
        return {
            "id": str(repo.id),
            "name": getattr(repo, "repo_name", getattr(repo, "name", "")),
            "path": getattr(repo, "state_path", getattr(repo, "path", "")),
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
        branch = payload.branch or getattr(repository, "default_branch", None)
        accepted_at = datetime.now(UTC).isoformat()
        node_ids: dict[tuple[str, str], uuid.UUID] = {}
        deleted_nodes = 0
        nodes_upserted = 0
        edges_upserted = 0

        changed_files = payload.sync_metadata.get("changed_files", [])
        paths_to_prune = set(payload.deleted_files)
        if isinstance(changed_files, list):
            paths_to_prune.update(str(path) for path in changed_files if isinstance(path, str) and path.strip())
        paths_to_prune.update(
            str(node.metadata.get("path"))
            for node in payload.nodes
            if isinstance(node.metadata.get("path"), str) and str(node.metadata.get("path")).strip()
        )

        if paths_to_prune:
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

        for node in payload.nodes:
            persisted = await self._graph_store.upsert_node(
                node.node_type,
                node.name,
                metadata={
                    "repo_id": str(repo_id),
                    "repository_name": repo_name,
                    "source": payload.source,
                    "payload_version": payload.payload_version,
                    "branch": branch,
                    "repo_path": payload.repo_path,
                    "diff_base": payload.diff_base,
                    **payload.sync_metadata,
                    **node.metadata,
                },
            )
            node_ids[(node.node_type, node.name)] = persisted.id
            nodes_upserted += 1

        for edge in payload.edges:
            source_key = (edge.source.node_type, edge.source.name)
            target_key = (edge.target.node_type, edge.target.name)

            if source_key not in node_ids:
                source_node = await self._graph_store.upsert_node(
                    edge.source.node_type,
                    edge.source.name,
                    metadata={
                        "repo_id": str(repo_id),
                        "repository_name": repo_name,
                        "source": payload.source,
                        "payload_version": payload.payload_version,
                        "branch": branch,
                        "repo_path": payload.repo_path,
                    },
                )
                node_ids[source_key] = source_node.id
                nodes_upserted += 1

            if target_key not in node_ids:
                target_node = await self._graph_store.upsert_node(
                    edge.target.node_type,
                    edge.target.name,
                    metadata={
                        "repo_id": str(repo_id),
                        "repository_name": repo_name,
                        "source": payload.source,
                        "payload_version": payload.payload_version,
                        "branch": branch,
                        "repo_path": payload.repo_path,
                    },
                )
                node_ids[target_key] = target_node.id
                nodes_upserted += 1

            await self._graph_store.upsert_edge(
                source_id=node_ids[source_key],
                target_id=node_ids[target_key],
                relation=edge.relation,
                weight=edge.weight,
            )
            edges_upserted += 1

        relationships = dict(getattr(repository, "relationships", {}) or {})
        relationships["graph_sync"] = {
            "payload_version": payload.payload_version,
            "source": payload.source,
            "branch": branch,
            "repo_path": payload.repo_path,
            "diff_base": payload.diff_base,
            "deleted_files": payload.deleted_files,
            "deleted_nodes": deleted_nodes,
            "nodes_upserted": nodes_upserted,
            "edges_upserted": edges_upserted,
            "accepted_at": accepted_at,
        }
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
