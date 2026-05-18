"""Qdrant Operational Store — Part 1: core + user/skill/session/workflow repos."""

from __future__ import annotations
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from minder.store.qdrant.client import QdrantClientWrapper
from minder.store.qdrant.crud import CollectionCRUD, _Doc, _now, _uid


class QdrantOperationalStore:
    """Qdrant-backed operational store implementing IOperationalStore."""

    def __init__(self, client: QdrantClientWrapper) -> None:
        self._client = client
        self._c = client.client
        self._p = client.prefix
        self._collections: dict[str, CollectionCRUD] = {}

    def _col(self, name: str, vec_size: int = 4) -> CollectionCRUD:
        key = f"{self._p}{name}"
        if key not in self._collections:
            self._collections[key] = CollectionCRUD(self._c, key, vec_size)
        return self._collections[key]

    async def init_db(self) -> None:
        for n in (
            "users",
            "skills",
            "prompts",
            "sessions",
            "workflows",
            "repositories",
            "workflow_states",
            "documents",
            "history",
            "errors",
            "rules",
            "feedback",
            "clients",
            "client_api_keys",
            "client_sessions",
            "audit_logs",
            "admin_jobs",
            "agents",
            "checkpoints",
        ):
            await self._col(n).ensure()

    async def dispose(self) -> None:
        await self._client.close()

    # -- Prompts --
    async def create_prompt(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        kw.setdefault("company_id", "default")
        kw.setdefault("arguments", [])
        return await self._col("prompts").insert(kw, kw.pop("id"))

    async def get_prompt_by_id(self, prompt_id: uuid.UUID) -> Any:
        return await self._col("prompts").get(_uid(prompt_id))

    async def get_prompt_by_name(self, name: str) -> Any:
        return await self._col("prompts").find_one("name", name)

    async def list_prompts(self) -> list[Any]:
        return await self._col("prompts").find_many()

    async def update_prompt(self, prompt_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self.get_prompt_by_id(prompt_id)
        return await self._col("prompts").update(_uid(prompt_id), kw)

    async def delete_prompt(self, prompt_id: uuid.UUID) -> None:
        await self._col("prompts").delete(_uid(prompt_id))

    # -- Users --
    async def create_user(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        kw.setdefault("company_id", "default")
        kw.setdefault("is_active", True)
        kw.setdefault("settings", {})
        kw.setdefault("last_login", None)
        return await self._col("users").insert(kw, kw.pop("id"))

    async def get_user_by_id(self, user_id: uuid.UUID) -> Any:
        return await self._col("users").get(_uid(user_id))

    async def get_user_by_email(self, email: str) -> Any:
        return await self._col("users").find_one("email", email)

    async def get_user_by_username(self, username: str) -> Any:
        return await self._col("users").find_one("username", username)

    async def list_users(self, active_only: bool = True) -> list[Any]:
        f = {"is_active": True} if active_only else None
        return await self._col("users").find_many(f)

    async def update_user(self, user_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self.get_user_by_id(user_id)
        return await self._col("users").update(_uid(user_id), kw)

    async def delete_user(self, user_id: uuid.UUID) -> None:
        await self._col("users").delete(_uid(user_id))

    async def has_admin_users(self) -> bool:
        r = await self._col("users").find_one("role", "admin")
        return r is not None

    # -- Skills --
    async def create_skill(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        kw.setdefault("company_id", "default")
        kw.setdefault("usage_count", 0)
        kw.setdefault("quality_score", 0.0)
        kw.setdefault("deprecated", False)
        kw.setdefault("tags", [])
        kw.setdefault("embedding", None)
        kw.setdefault("source_metadata", None)
        kw.setdefault("excerpt_kind", "none")
        return await self._col("skills").insert(kw, kw.pop("id"))

    async def get_skill_by_id(self, skill_id: uuid.UUID) -> Any:
        return await self._col("skills").get(_uid(skill_id))

    async def list_skills(self) -> list[Any]:
        return await self._col("skills").find_many()

    async def list_skills_by_kind(
        self, *, is_memory: bool, exclude_deprecated: bool = True
    ) -> list[Any]:
        all_skills = await self.list_skills()
        _mem_langs = {"markdown", "text", "en", "vi", "", None}
        result = []
        for s in all_skills:
            sm = s._data.get("source_metadata")
            lang = s._data.get("language")
            is_mem = sm is None and lang in _mem_langs
            if is_memory and is_mem:
                result.append(s)
            elif not is_memory and not is_mem:
                if exclude_deprecated and s._data.get("deprecated"):
                    continue
                result.append(s)
        return result

    async def update_skill(self, skill_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self.get_skill_by_id(skill_id)
        return await self._col("skills").update(_uid(skill_id), kw)

    async def delete_skill(self, skill_id: uuid.UUID) -> None:
        await self._col("skills").delete(_uid(skill_id))

    # -- Sessions --
    async def create_session(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        kw.setdefault("company_id", "default")
        for uf in ("user_id", "client_id", "repo_id"):
            if uf in kw and isinstance(kw[uf], uuid.UUID):
                kw[uf] = _uid(kw[uf])
        kw.setdefault("name", None)
        kw.setdefault("project_context", {})
        kw.setdefault("active_skills", {})
        kw.setdefault("state", {})
        kw.setdefault("ttl", 86400)
        kw.setdefault("last_active", _now().isoformat())
        return await self._col("sessions").insert(kw, kw.pop("id"))

    async def get_session_by_id(self, session_id: uuid.UUID) -> Any:
        return await self._col("sessions").get(_uid(session_id))

    async def get_sessions_by_user(self, user_id: uuid.UUID) -> list[Any]:
        return await self._col("sessions").find_many(
            {"user_id": _uid(user_id)}, order_field="last_active"
        )

    async def get_sessions_by_client(self, client_id: uuid.UUID) -> list[Any]:
        return await self._col("sessions").find_many(
            {"client_id": _uid(client_id)}, order_field="last_active"
        )

    async def find_session_by_name(
        self,
        name: str,
        *,
        user_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
    ) -> Any:
        f: dict[str, Any] = {"name": name}
        if client_id:
            f["client_id"] = _uid(client_id)
        elif user_id:
            f["user_id"] = _uid(user_id)
        docs = await self._col("sessions").find_many(
            f, limit=1, order_field="last_active"
        )
        return docs[0] if docs else None

    async def update_session(self, session_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self.get_session_by_id(session_id)
        kw["last_active"] = _now().isoformat()
        return await self._col("sessions").update(_uid(session_id), kw)

    async def list_sessions(self) -> list[Any]:
        return await self._col("sessions").find_many(order_field="last_active")

    async def delete_session(self, session_id: uuid.UUID) -> None:
        await self._col("sessions").delete(_uid(session_id))

    async def cleanup_expired_sessions(
        self,
        *,
        now: datetime | None = None,
        user_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        ref = now or _now()
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=UTC)
        f: dict[str, Any] = {}
        if user_id:
            f["user_id"] = _uid(user_id)
        if client_id:
            f["client_id"] = _uid(client_id)
        sessions = await self._col("sessions").find_many(f if f else None)
        expired_ids: list[str] = []
        for s in sessions:
            ttl = int(s._data.get("ttl", 0) or 0)
            if ttl <= 0:
                continue
            la = s._data.get("last_active") or s._data.get("created_at")
            if isinstance(la, str):
                try:
                    from datetime import datetime as dt

                    base = dt.fromisoformat(la)
                    if base.tzinfo is None:
                        base = base.replace(tzinfo=UTC)
                except Exception:
                    continue
            elif isinstance(la, datetime):
                base = la if la.tzinfo else la.replace(tzinfo=UTC)
            else:
                continue
            if base + timedelta(seconds=ttl) <= ref:
                expired_ids.append(str(s._data.get("id", "")))
        if not expired_ids:
            return {"deleted_sessions": 0, "deleted_history": 0}
        h_del = await self._col("history").delete_many({"session_id": expired_ids})
        s_del = 0
        for sid in expired_ids:
            await self._col("sessions").delete(sid)
            s_del += 1
        return {"deleted_sessions": s_del, "deleted_history": h_del}

    # -- Workflows --
    async def create_workflow(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        kw.setdefault("company_id", "default")
        kw.setdefault("version", 1)
        kw.setdefault("steps", [])
        kw.setdefault("policies", {})
        kw.setdefault("default_for_repo", False)
        return await self._col("workflows").insert(kw, kw.pop("id"))

    async def get_workflow_by_id(self, wf_id: uuid.UUID) -> Any:
        return await self._col("workflows").get(_uid(wf_id))

    async def get_workflow_by_name(self, name: str) -> Any:
        return await self._col("workflows").find_one("name", name)

    async def list_workflows(self) -> list[Any]:
        return await self._col("workflows").find_many()

    async def update_workflow(self, wf_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self.get_workflow_by_id(wf_id)
        return await self._col("workflows").update(_uid(wf_id), kw)

    async def delete_workflow(self, wf_id: uuid.UUID) -> None:
        await self._col("workflows").delete(_uid(wf_id))

    # -- Repositories --
    async def create_repository(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        kw.setdefault("company_id", "default")
        for uf in ("workflow_id",):
            if uf in kw and isinstance(kw[uf], uuid.UUID):
                kw[uf] = _uid(kw[uf])
        kw.setdefault("workflow_id", None)
        kw.setdefault("state_path", ".minder")
        kw.setdefault("context_snapshot", {})
        kw.setdefault("relationships", {})
        return await self._col("repositories").insert(kw, kw.pop("id"))

    async def get_repository_by_id(self, repo_id: uuid.UUID) -> Any:
        return await self._col("repositories").get(_uid(repo_id))

    async def get_repository_by_name(self, repo_name: str) -> Any:
        return await self._col("repositories").find_one("repo_name", repo_name)

    async def list_repositories(self) -> list[Any]:
        return await self._col("repositories").find_many()

    async def update_repository(self, repo_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self.get_repository_by_id(repo_id)
        return await self._col("repositories").update(_uid(repo_id), kw)

    async def delete_repository(self, repo_id: uuid.UUID) -> None:
        await self._col("repositories").delete(_uid(repo_id))

    # -- WorkflowState --
    async def create_workflow_state(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        for uf in ("repo_id", "session_id"):
            if uf in kw and isinstance(kw[uf], uuid.UUID):
                kw[uf] = _uid(kw[uf])
        kw.setdefault("completed_steps", [])
        kw.setdefault("blocked_by", [])
        kw.setdefault("artifacts", {})
        kw.setdefault("next_step", None)
        return await self._col("workflow_states").insert(kw, kw.pop("id"))

    async def get_workflow_state_by_id(self, state_id: uuid.UUID) -> Any:
        return await self._col("workflow_states").get(_uid(state_id))

    async def get_workflow_state_by_repo(self, repo_id: uuid.UUID) -> Any:
        return await self._col("workflow_states").find_one("repo_id", _uid(repo_id))

    async def update_workflow_state(self, state_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self.get_workflow_state_by_id(state_id)
        return await self._col("workflow_states").update(_uid(state_id), kw)

    async def delete_workflow_state(self, state_id: uuid.UUID) -> None:
        await self._col("workflow_states").delete(_uid(state_id))

    # -- Documents --
    async def create_document(
        self,
        title: str,
        content: str,
        doc_type: str,
        source_path: str,
        project: str,
        *,
        chunks: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> Any:
        kw: dict[str, Any] = {
            "id": _uid(uuid.uuid4()),
            "title": title,
            "content": content,
            "doc_type": doc_type,
            "source_path": source_path,
            "project": project,
            "chunks": chunks,
            "embedding": embedding,
        }
        return await self._col("documents").insert(kw, kw.pop("id"))

    async def get_document_by_path(
        self, source_path: str, *, project: str | None = None
    ) -> Any:
        f: dict[str, Any] = {"source_path": source_path}
        if project:
            f["project"] = project
        docs = await self._col("documents").find_many(f, limit=1)
        return docs[0] if docs else None

    async def get_documents_by_ids(self, doc_ids: list[uuid.UUID]) -> list[Any]:
        if not doc_ids:
            return []
        await self._col("documents").ensure()
        results = await self._c.retrieve(
            self._col("documents")._collection,
            ids=[_uid(d) for d in doc_ids],
            with_payload=True,
        )
        out = []
        for r in results:
            p = dict(r.payload or {})
            p["id"] = str(r.id)
            out.append(_Doc(p))
        return out

    async def list_documents(self, project: str | None = None) -> list[Any]:
        f = {"project": project} if project else None
        return await self._col("documents").find_many(f)

    async def upsert_document(
        self,
        *,
        title: str,
        content: str,
        doc_type: str,
        source_path: str,
        project: str,
        chunks: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> Any:
        existing = await self.get_document_by_path(source_path, project=project)
        if existing:
            return await self._col("documents").update(
                str(existing.id),
                {
                    "title": title,
                    "content": content,
                    "doc_type": doc_type,
                    "chunks": chunks,
                    "embedding": embedding,
                },
            )
        return await self.create_document(
            title,
            content,
            doc_type,
            source_path,
            project,
            chunks=chunks,
            embedding=embedding,
        )

    async def delete_documents_not_in_paths(
        self, *, project: str, keep_paths: set[str]
    ) -> None:
        docs = await self.list_documents(project=project)
        for d in docs:
            if d._data.get("source_path") not in keep_paths:
                await self._col("documents").delete(str(d.id))

    # -- History --
    async def create_history(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        reasoning_trace: str | None = None,
        tool_calls: dict[str, Any] | None = None,
        tokens_used: int = 0,
        latency_ms: int = 0,
    ) -> Any:
        kw: dict[str, Any] = {
            "id": _uid(uuid.uuid4()),
            "session_id": _uid(session_id),
            "role": role,
            "content": content,
            "reasoning_trace": reasoning_trace,
            "tool_calls": tool_calls,
            "tokens_used": tokens_used,
            "latency_ms": latency_ms,
        }
        return await self._col("history").insert(kw, kw.pop("id"))

    async def list_history_for_session(self, session_id: uuid.UUID) -> list[Any]:
        return await self._col("history").find_many(
            {"session_id": _uid(session_id)}, order_field="created_at", order_desc=False
        )

    async def list_history_for_user(self, user_id: uuid.UUID) -> list[Any]:
        return await self._col("history").find_many(
            {"user_id": _uid(user_id)}, order_field="created_at", order_desc=False
        )

    async def delete_history_for_session(self, session_id: uuid.UUID) -> int:
        return await self._col("history").delete_many({"session_id": _uid(session_id)})

    # -- Errors --
    async def create_error(
        self,
        error_code: str,
        error_message: str,
        stack_trace: str | None = None,
        context: dict[str, Any] | None = None,
        resolution: str | None = None,
        embedding: list[float] | None = None,
        resolved: bool = False,
    ) -> Any:
        kw: dict[str, Any] = {
            "id": _uid(uuid.uuid4()),
            "error_code": error_code,
            "error_message": error_message,
            "stack_trace": stack_trace,
            "context": context,
            "resolution": resolution,
            "embedding": embedding,
            "resolved": resolved,
        }
        return await self._col("errors").insert(kw, kw.pop("id"))

    async def list_errors(self) -> list[Any]:
        return await self._col("errors").find_many()

    async def search_errors(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        errors = await self.list_errors()
        q_lower = query.lower()
        results = []
        for e in errors:
            msg = str(e._data.get("error_message", "")).lower()
            code = str(e._data.get("error_code", "")).lower()
            if q_lower in msg or q_lower in code:
                results.append(e._data)
        return results[:limit]

    # -- Rules --
    async def create_rule(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        kw.setdefault("is_active", True)
        return await self._col("rules").insert(kw, kw.pop("id"))

    async def get_rule_by_id(self, rule_id: uuid.UUID) -> Any:
        return await self._col("rules").get(_uid(rule_id))

    async def list_rules(self) -> list[Any]:
        return await self._col("rules").find_many()

    async def list_by_scope(self, scope: str) -> list[Any]:
        return await self._col("rules").find_many({"scope": scope})

    async def list_active(self) -> list[Any]:
        return await self._col("rules").find_many({"is_active": True})

    async def update_rule(self, rule_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self.get_rule_by_id(rule_id)
        return await self._col("rules").update(_uid(rule_id), kw)

    async def delete_rule(self, rule_id: uuid.UUID) -> None:
        await self._col("rules").delete(_uid(rule_id))

    # -- Feedback --
    async def create_feedback(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        return await self._col("feedback").insert(kw, kw.pop("id"))

    async def get_feedback_by_id(self, fb_id: uuid.UUID) -> Any:
        return await self._col("feedback").get(_uid(fb_id))

    async def list_feedback(self) -> list[Any]:
        return await self._col("feedback").find_many()

    async def list_by_entity(self, entity_type: str, entity_id: uuid.UUID) -> list[Any]:
        return await self._col("feedback").find_many(
            {"entity_type": entity_type, "entity_id": _uid(entity_id)}
        )

    async def average_rating(self, entity_id: uuid.UUID) -> float | None:
        items = await self._col("feedback").find_many({"entity_id": _uid(entity_id)})
        if not items:
            return None
        ratings = [
            i._data.get("rating", 0) for i in items if i._data.get("rating") is not None
        ]
        return sum(ratings) / len(ratings) if ratings else None

    async def update_feedback(self, fb_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self.get_feedback_by_id(fb_id)
        return await self._col("feedback").update(_uid(fb_id), kw)

    async def delete_feedback(self, fb_id: uuid.UUID) -> None:
        await self._col("feedback").delete(_uid(fb_id))

    # -- Clients --
    async def create_client(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        for uf in ("created_by_user_id",):
            if uf in kw and isinstance(kw[uf], uuid.UUID):
                kw[uf] = _uid(kw[uf])
        kw.setdefault("description", "")
        kw.setdefault("status", "active")
        kw.setdefault("transport_modes", ["sse", "stdio"])
        kw.setdefault("tool_scopes", [])
        kw.setdefault("repo_scopes", [])
        kw.setdefault("workflow_scopes", [])
        kw.setdefault("rate_limit_policy", {})
        return await self._col("clients").insert(kw, kw.pop("id"))

    async def get_client_by_id(self, client_id: uuid.UUID) -> Any:
        return await self._col("clients").get(_uid(client_id))

    async def get_client_by_slug(self, slug: str) -> Any:
        return await self._col("clients").find_one("slug", slug)

    async def list_clients(self) -> list[Any]:
        return await self._col("clients").find_many()

    async def update_client(self, client_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self.get_client_by_id(client_id)
        return await self._col("clients").update(_uid(client_id), kw)

    async def create_client_api_key(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        for uf in ("client_id", "created_by_user_id"):
            if uf in kw and isinstance(kw[uf], uuid.UUID):
                kw[uf] = _uid(kw[uf])
        kw.setdefault("status", "active")
        kw.setdefault("last_used_at", None)
        kw.setdefault("expires_at", None)
        kw.setdefault("revoked_at", None)
        return await self._col("client_api_keys").insert(kw, kw.pop("id"))

    async def list_client_api_keys(self, client_id: uuid.UUID) -> list[Any]:
        return await self._col("client_api_keys").find_many(
            {"client_id": _uid(client_id)}
        )

    async def update_client_api_key(self, key_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self._col("client_api_keys").get(_uid(key_id))
        return await self._col("client_api_keys").update(_uid(key_id), kw)

    async def create_client_session(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        if "client_id" in kw and isinstance(kw["client_id"], uuid.UUID):
            kw["client_id"] = _uid(kw["client_id"])
        kw.setdefault("status", "active")
        kw.setdefault("scopes", [])
        kw.setdefault("issued_at", _now().isoformat())
        kw.setdefault("last_seen_at", None)
        kw.setdefault("session_metadata", {})
        return await self._col("client_sessions").insert(kw, kw.pop("id"))

    async def get_client_session_by_token_id(self, token_id: str) -> Any:
        return await self._col("client_sessions").find_one("access_token_id", token_id)

    async def update_client_session(self, session_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self._col("client_sessions").get(_uid(session_id))
        return await self._col("client_sessions").update(_uid(session_id), kw)

    async def count_active_client_sessions(self) -> int:
        return await self._col("client_sessions").count({"status": "active"})

    async def create_audit_log(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        kw.setdefault("audit_metadata", {})
        return await self._col("audit_logs").insert(kw, kw.pop("id"))

    async def list_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        event_type: str | None = None,
        outcome: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Any]:
        f: dict[str, Any] = {}
        if actor_id:
            f["actor_id"] = actor_id
        if event_type:
            f["event_type"] = event_type
        if outcome:
            f["outcome"] = outcome
        return await self._col("audit_logs").find_many(
            f if f else None,
            limit=limit or 1000,
            offset=offset,
            order_field="created_at",
        )

    async def count_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        event_type: str | None = None,
        outcome: str | None = None,
    ) -> int:
        f: dict[str, Any] = {}
        if actor_id:
            f["actor_id"] = actor_id
        if event_type:
            f["event_type"] = event_type
        if outcome:
            f["outcome"] = outcome
        return await self._col("audit_logs").count(f if f else None)

    async def get_audit_summary(
        self,
        *,
        actor_id: str | None = None,
        event_type: str | None = None,
        outcome: str | None = None,
        group_by: str = "event_type",
    ) -> dict[str, int]:
        logs = await self.list_audit_logs(
            actor_id=actor_id, event_type=event_type, outcome=outcome
        )
        counter: dict[str, int] = {}
        for log in logs:
            key = "." in group_by and group_by.split(".", 1) or (group_by,)
            if len(key) == 2:
                val = (log._data.get(key[0]) or {}).get(key[1], "unknown")
            else:
                val = log._data.get(key[0], "unknown")
            val = str(val) if val is not None else "unknown"
            counter[val] = counter.get(val, 0) + 1
        return counter

    # -- Admin Jobs --
    async def create_admin_job(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        if "requested_by_user_id" in kw and isinstance(
            kw["requested_by_user_id"], uuid.UUID
        ):
            kw["requested_by_user_id"] = _uid(kw["requested_by_user_id"])
        kw.setdefault("company_id", "default")
        kw.setdefault("status", "queued")
        kw.setdefault("payload", {})
        kw.setdefault("result_payload", None)
        kw.setdefault("error_message", None)
        kw.setdefault("progress_current", 0)
        kw.setdefault("progress_total", 0)
        kw.setdefault("message", None)
        kw.setdefault("events", [])
        kw.setdefault("started_at", None)
        kw.setdefault("finished_at", None)
        return await self._col("admin_jobs").insert(kw, kw.pop("id"))

    async def get_admin_job_by_id(self, job_id: uuid.UUID) -> Any:
        return await self._col("admin_jobs").get(_uid(job_id))

    async def list_admin_jobs(
        self,
        *,
        job_type: str | None = None,
        status: str | None = None,
        requested_by_user_id: uuid.UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Any]:
        f: dict[str, Any] = {}
        if job_type:
            f["job_type"] = job_type
        if status:
            f["status"] = status
        if requested_by_user_id:
            f["requested_by_user_id"] = _uid(requested_by_user_id)
        return await self._col("admin_jobs").find_many(
            f if f else None,
            limit=limit or 1000,
            offset=offset,
            order_field="created_at",
        )

    async def update_admin_job(self, job_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self.get_admin_job_by_id(job_id)
        if "requested_by_user_id" in kw and isinstance(
            kw["requested_by_user_id"], uuid.UUID
        ):
            kw["requested_by_user_id"] = _uid(kw["requested_by_user_id"])
        return await self._col("admin_jobs").update(_uid(job_id), kw)

    # -- Agents --
    async def create_agent(self, **kw: Any) -> Any:
        kw.setdefault("id", _uid(uuid.uuid4()))
        kw["id"] = _uid(kw["id"])
        kw.setdefault("workflow_steps", [])
        kw.setdefault("tags", [])
        kw.setdefault("is_default", False)
        kw.setdefault("artifact_types", [])
        return await self._col("agents").insert(kw, kw.pop("id"))

    async def get_agent_by_id(self, agent_id: uuid.UUID) -> Any:
        return await self._col("agents").get(_uid(agent_id))

    async def get_agent_by_name(self, name: str) -> Any:
        return await self._col("agents").find_one("name", name)

    async def list_agents(
        self,
        *,
        workflow_step: str | None = None,
        tag: str | None = None,
        is_default: bool | None = None,
    ) -> list[Any]:
        agents = await self._col("agents").find_many()
        if workflow_step:
            agents = [
                a
                for a in agents
                if workflow_step in (a._data.get("workflow_steps") or [])
            ]
        if tag:
            agents = [a for a in agents if tag in (a._data.get("tags") or [])]
        if is_default is not None:
            agents = [a for a in agents if a._data.get("is_default") == is_default]
        return agents

    async def upsert_agent(self, name: str, **kw: Any) -> Any:
        existing = await self.get_agent_by_name(name)
        if existing:
            return await self._col("agents").update(str(existing.id), kw)
        kw["name"] = name
        return await self.create_agent(**kw)

    async def update_agent(self, agent_id: uuid.UUID, **kw: Any) -> Any:
        if not kw:
            return await self.get_agent_by_id(agent_id)
        return await self._col("agents").update(_uid(agent_id), kw)

    async def delete_agent(self, agent_id: uuid.UUID) -> None:
        await self._col("agents").delete(_uid(agent_id))

    # -- Checkpoints --
    async def get_checkpoint(self, thread_id: str) -> dict[str, Any] | None:
        doc = await self._col("checkpoints").find_one("thread_id", thread_id)
        return doc._data if doc else None

    async def save_checkpoint(
        self,
        thread_id: str,
        checkpoint_id: str,
        checkpoint: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        import base64

        existing = await self._col("checkpoints").find_one("thread_id", thread_id)
        payload: dict[str, Any] = {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "checkpoint_b64": base64.b64encode(checkpoint).decode(),
            "metadata": metadata or {},
        }
        if existing:
            await self._col("checkpoints").set_payload(str(existing.id), payload)
        else:
            payload["id"] = _uid(uuid.uuid4())
            await self._col("checkpoints").insert(payload, payload.pop("id"))

    async def list_checkpoints(
        self, thread_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        docs = await self._col("checkpoints").find_many(
            {"thread_id": thread_id}, limit=limit, order_field="created_at"
        )
        return [d._data for d in docs]
