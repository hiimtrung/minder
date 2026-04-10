"""
MongoDB Operational Store — Motor-based adapter implementing IOperationalStore.

This is the MongoDB-backed replacement for the SQLite RelationalStore.
It implements all domain repository interfaces through a single composite class,
matching the current RelationalStore API surface for backwards compatibility.
"""

from __future__ import annotations

import math
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any, cast

from motor.motor_asyncio import AsyncIOMotorDatabase

from minder.store.mongodb.client import MongoClient
from minder.store.mongodb.indexes import ensure_indexes


def _uuid_to_str(value: uuid.UUID) -> str:
    """Serialize UUID to string for MongoDB storage."""
    return str(value)


def _str_to_uuid(value: str) -> uuid.UUID:
    """Deserialize string to UUID from MongoDB storage."""
    return uuid.UUID(value)


def _now() -> datetime:
    return datetime.now(UTC)


class _MongoDoc:
    """
    Lightweight wrapper around a MongoDB document dict to provide
    attribute-style access, matching SQLAlchemy model access patterns.

    This lets existing application code like `user.email` work without
    changes, whether the object came from SQLAlchemy or MongoDB.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        # Convert _id to id if present
        if "_id" in self._data and "id" not in self._data:
            self._data["id"] = self._data.pop("_id")
        # Convert string UUIDs back to uuid.UUID for id fields
        for field in ("id", "user_id", "repo_id", "session_id", "workflow_id"):
            val = self._data.get(field)
            if isinstance(val, str):
                try:
                    self._data[field] = uuid.UUID(val)
                except ValueError:
                    pass

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"MongoDoc has no attribute '{name}'")

    def __repr__(self) -> str:
        return f"MongoDoc({self._data!r})"


def _to_doc(data: dict[str, Any]) -> _MongoDoc:
    """Convert a raw MongoDB document to an attribute-accessible object."""
    return _MongoDoc(data)


class MongoOperationalStore:
    """
    MongoDB-backed operational store implementing the full
    IOperationalStore interface (user, skill, session, workflow,
    repository, workflow_state, document, history, error repos).
    """

    def __init__(self, client: MongoClient) -> None:
        self._client = client
        self._db: AsyncIOMotorDatabase = client.db  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init_db(self) -> None:
        """Create all indexes (idempotent)."""
        await ensure_indexes(self._db)

    async def dispose(self) -> None:
        """Close the MongoDB client."""
        await self._client.close()

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------

    async def create_user(self, **kwargs: Any) -> _MongoDoc:
        if "id" not in kwargs:
            kwargs["id"] = _uuid_to_str(uuid.uuid4())
        else:
            kwargs["id"] = _uuid_to_str(kwargs["id"])
        for field in ("company_id",):
            kwargs.setdefault(field, "default")
        kwargs.setdefault("is_active", True)
        kwargs.setdefault("settings", {})
        kwargs.setdefault("created_at", _now())
        kwargs.setdefault("last_login", None)
        kwargs["_id"] = kwargs.pop("id")
        await self._db.users.insert_one(kwargs)
        return _to_doc(kwargs)

    async def get_user_by_id(self, user_id: uuid.UUID) -> _MongoDoc | None:
        doc = await self._db.users.find_one({"_id": _uuid_to_str(user_id)})
        return _to_doc(doc) if doc else None

    async def get_user_by_email(self, email: str) -> _MongoDoc | None:
        doc = await self._db.users.find_one({"email": email})
        return _to_doc(doc) if doc else None

    async def get_user_by_username(self, username: str) -> _MongoDoc | None:
        doc = await self._db.users.find_one({"username": username})
        return _to_doc(doc) if doc else None

    async def list_users(self, active_only: bool = True) -> list[_MongoDoc]:
        query: dict[str, Any] = {}
        if active_only:
            query["is_active"] = True
        cursor = self._db.users.find(query)
        return [_to_doc(doc) async for doc in cursor]

    async def update_user(self, user_id: uuid.UUID, **kwargs: Any) -> _MongoDoc | None:
        if not kwargs:
            return await self.get_user_by_id(user_id)
        await self._db.users.update_one(
            {"_id": _uuid_to_str(user_id)}, {"$set": kwargs}
        )
        return await self.get_user_by_id(user_id)

    async def delete_user(self, user_id: uuid.UUID) -> None:
        await self._db.users.delete_one({"_id": _uuid_to_str(user_id)})

    async def has_admin_users(self) -> bool:
        doc = await self._db.users.find_one({"role": "admin"})
        return doc is not None

    # ------------------------------------------------------------------
    # Client Gateway
    # ------------------------------------------------------------------

    async def create_client(self, **kwargs: Any) -> _MongoDoc:
        if "id" not in kwargs:
            kwargs["id"] = _uuid_to_str(uuid.uuid4())
        else:
            kwargs["id"] = _uuid_to_str(kwargs["id"])
        if "created_by_user_id" in kwargs and isinstance(kwargs["created_by_user_id"], uuid.UUID):
            kwargs["created_by_user_id"] = _uuid_to_str(kwargs["created_by_user_id"])
        kwargs.setdefault("description", "")
        kwargs.setdefault("status", "active")
        kwargs.setdefault("transport_modes", ["sse", "stdio"])
        kwargs.setdefault("tool_scopes", [])
        kwargs.setdefault("repo_scopes", [])
        kwargs.setdefault("workflow_scopes", [])
        kwargs.setdefault("rate_limit_policy", {})
        kwargs.setdefault("created_at", _now())
        kwargs.setdefault("updated_at", _now())
        kwargs["_id"] = kwargs.pop("id")
        await self._db.clients.insert_one(kwargs)
        return _to_doc(kwargs)

    async def get_client_by_id(self, client_id: uuid.UUID) -> _MongoDoc | None:
        doc = await self._db.clients.find_one({"_id": _uuid_to_str(client_id)})
        return _to_doc(doc) if doc else None

    async def get_client_by_slug(self, slug: str) -> _MongoDoc | None:
        doc = await self._db.clients.find_one({"slug": slug})
        return _to_doc(doc) if doc else None

    async def list_clients(self) -> list[_MongoDoc]:
        cursor = self._db.clients.find()
        return [_to_doc(doc) async for doc in cursor]

    async def update_client(self, client_id: uuid.UUID, **kwargs: Any) -> _MongoDoc | None:
        if not kwargs:
            return await self.get_client_by_id(client_id)
        kwargs["updated_at"] = _now()
        await self._db.clients.update_one(
            {"_id": _uuid_to_str(client_id)},
            {"$set": kwargs},
        )
        return await self.get_client_by_id(client_id)

    async def create_client_api_key(self, **kwargs: Any) -> _MongoDoc:
        if "id" not in kwargs:
            kwargs["id"] = _uuid_to_str(uuid.uuid4())
        else:
            kwargs["id"] = _uuid_to_str(kwargs["id"])
        for uuid_field in ("client_id", "created_by_user_id"):
            if uuid_field in kwargs and isinstance(kwargs[uuid_field], uuid.UUID):
                kwargs[uuid_field] = _uuid_to_str(kwargs[uuid_field])
        kwargs.setdefault("status", "active")
        kwargs.setdefault("last_used_at", None)
        kwargs.setdefault("created_at", _now())
        kwargs.setdefault("expires_at", None)
        kwargs.setdefault("revoked_at", None)
        kwargs["_id"] = kwargs.pop("id")
        await self._db.client_api_keys.insert_one(kwargs)
        return _to_doc(kwargs)

    async def list_client_api_keys(self, client_id: uuid.UUID) -> list[_MongoDoc]:
        cursor = self._db.client_api_keys.find({"client_id": _uuid_to_str(client_id)})
        return [_to_doc(doc) async for doc in cursor]

    async def update_client_api_key(self, key_id: uuid.UUID, **kwargs: Any) -> _MongoDoc | None:
        if not kwargs:
            doc = await self._db.client_api_keys.find_one({"_id": _uuid_to_str(key_id)})
            return _to_doc(doc) if doc else None
        await self._db.client_api_keys.update_one(
            {"_id": _uuid_to_str(key_id)},
            {"$set": kwargs},
        )
        doc = await self._db.client_api_keys.find_one({"_id": _uuid_to_str(key_id)})
        return _to_doc(doc) if doc else None

    async def create_client_session(self, **kwargs: Any) -> _MongoDoc:
        if "id" not in kwargs:
            kwargs["id"] = _uuid_to_str(uuid.uuid4())
        else:
            kwargs["id"] = _uuid_to_str(kwargs["id"])
        if "client_id" in kwargs and isinstance(kwargs["client_id"], uuid.UUID):
            kwargs["client_id"] = _uuid_to_str(kwargs["client_id"])
        kwargs.setdefault("status", "active")
        kwargs.setdefault("scopes", [])
        kwargs.setdefault("issued_at", _now())
        kwargs.setdefault("last_seen_at", None)
        kwargs.setdefault("session_metadata", {})
        kwargs["_id"] = kwargs.pop("id")
        await self._db.client_sessions.insert_one(kwargs)
        return _to_doc(kwargs)

    async def get_client_session_by_token_id(self, token_id: str) -> _MongoDoc | None:
        doc = await self._db.client_sessions.find_one({"access_token_id": token_id})
        return _to_doc(doc) if doc else None

    async def update_client_session(self, session_id: uuid.UUID, **kwargs: Any) -> _MongoDoc | None:
        if not kwargs:
            doc = await self._db.client_sessions.find_one({"_id": _uuid_to_str(session_id)})
            return _to_doc(doc) if doc else None
        await self._db.client_sessions.update_one(
            {"_id": _uuid_to_str(session_id)},
            {"$set": kwargs},
        )
        doc = await self._db.client_sessions.find_one({"_id": _uuid_to_str(session_id)})
        return _to_doc(doc) if doc else None

    async def create_audit_log(self, **kwargs: Any) -> _MongoDoc:
        if "id" not in kwargs:
            kwargs["id"] = _uuid_to_str(uuid.uuid4())
        else:
            kwargs["id"] = _uuid_to_str(kwargs["id"])
        kwargs.setdefault("audit_metadata", {})
        kwargs.setdefault("created_at", _now())
        kwargs["_id"] = kwargs.pop("id")
        await self._db.audit_logs.insert_one(kwargs)
        return _to_doc(kwargs)

    async def list_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[_MongoDoc]:
        query: dict[str, Any] = {}
        if actor_id is not None:
            query["actor_id"] = actor_id
        cursor = self._db.audit_logs.find(query).sort("created_at", -1).skip(offset)
        if limit is not None:
            cursor = cursor.limit(limit)
        return [_to_doc(doc) async for doc in cursor]

    async def count_audit_logs(self, *, actor_id: str | None = None) -> int:
        query: dict[str, Any] = {}
        if actor_id is not None:
            query["actor_id"] = actor_id
        return int(await self._db.audit_logs.count_documents(query))

    # ------------------------------------------------------------------
    # Skill
    # ------------------------------------------------------------------

    async def create_skill(self, **kwargs: Any) -> _MongoDoc:
        if "id" not in kwargs:
            kwargs["id"] = _uuid_to_str(uuid.uuid4())
        else:
            kwargs["id"] = _uuid_to_str(kwargs["id"])
        kwargs.setdefault("company_id", "default")
        kwargs.setdefault("usage_count", 0)
        kwargs.setdefault("quality_score", 0.0)
        kwargs.setdefault("tags", [])
        kwargs.setdefault("embedding", None)
        kwargs.setdefault("created_at", _now())
        kwargs.setdefault("updated_at", _now())
        kwargs["_id"] = kwargs.pop("id")
        await self._db.skills.insert_one(kwargs)
        return _to_doc(kwargs)

    async def get_skill_by_id(self, skill_id: uuid.UUID) -> _MongoDoc | None:
        doc = await self._db.skills.find_one({"_id": _uuid_to_str(skill_id)})
        return _to_doc(doc) if doc else None

    async def list_skills(self) -> list[_MongoDoc]:
        cursor = self._db.skills.find()
        return [_to_doc(doc) async for doc in cursor]

    async def delete_skill(self, skill_id: uuid.UUID) -> None:
        await self._db.skills.delete_one({"_id": _uuid_to_str(skill_id)})

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    async def create_session(self, **kwargs: Any) -> _MongoDoc:
        if "id" not in kwargs:
            kwargs["id"] = _uuid_to_str(uuid.uuid4())
        else:
            kwargs["id"] = _uuid_to_str(kwargs["id"])
        kwargs.setdefault("company_id", "default")
        for uuid_field in ("user_id", "repo_id"):
            if uuid_field in kwargs and isinstance(kwargs[uuid_field], uuid.UUID):
                kwargs[uuid_field] = _uuid_to_str(kwargs[uuid_field])
        kwargs.setdefault("project_context", {})
        kwargs.setdefault("active_skills", {})
        kwargs.setdefault("state", {})
        kwargs.setdefault("ttl", 3600)
        kwargs.setdefault("created_at", _now())
        kwargs.setdefault("last_active", _now())
        kwargs["_id"] = kwargs.pop("id")
        await self._db.sessions.insert_one(kwargs)
        return _to_doc(kwargs)

    async def get_session_by_id(self, session_id: uuid.UUID) -> _MongoDoc | None:
        doc = await self._db.sessions.find_one({"_id": _uuid_to_str(session_id)})
        return _to_doc(doc) if doc else None

    async def get_sessions_by_user(self, user_id: uuid.UUID) -> list[_MongoDoc]:
        cursor = self._db.sessions.find({"user_id": _uuid_to_str(user_id)})
        return [_to_doc(doc) async for doc in cursor]

    async def update_session(self, session_id: uuid.UUID, **kwargs: Any) -> _MongoDoc | None:
        if not kwargs:
            return await self.get_session_by_id(session_id)
        kwargs["last_active"] = _now()
        await self._db.sessions.update_one(
            {"_id": _uuid_to_str(session_id)}, {"$set": kwargs}
        )
        return await self.get_session_by_id(session_id)

    async def delete_session(self, session_id: uuid.UUID) -> None:
        await self._db.sessions.delete_one({"_id": _uuid_to_str(session_id)})

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    async def create_workflow(self, **kwargs: Any) -> _MongoDoc:
        if "id" not in kwargs:
            kwargs["id"] = _uuid_to_str(uuid.uuid4())
        else:
            kwargs["id"] = _uuid_to_str(kwargs["id"])
        kwargs.setdefault("company_id", "default")
        kwargs.setdefault("version", 1)
        kwargs.setdefault("steps", [])
        kwargs.setdefault("policies", {})
        kwargs.setdefault("default_for_repo", False)
        kwargs.setdefault("created_at", _now())
        kwargs.setdefault("updated_at", _now())
        kwargs["_id"] = kwargs.pop("id")
        await self._db.workflows.insert_one(kwargs)
        return _to_doc(kwargs)

    async def get_workflow_by_id(self, workflow_id: uuid.UUID) -> _MongoDoc | None:
        doc = await self._db.workflows.find_one({"_id": _uuid_to_str(workflow_id)})
        return _to_doc(doc) if doc else None

    async def get_workflow_by_name(self, name: str) -> _MongoDoc | None:
        doc = await self._db.workflows.find_one({"name": name})
        return _to_doc(doc) if doc else None

    async def list_workflows(self) -> list[_MongoDoc]:
        cursor = self._db.workflows.find()
        return [_to_doc(doc) async for doc in cursor]

    async def update_workflow(self, workflow_id: uuid.UUID, **kwargs: Any) -> _MongoDoc | None:
        if not kwargs:
            return await self.get_workflow_by_id(workflow_id)
        kwargs["updated_at"] = _now()
        await self._db.workflows.update_one(
            {"_id": _uuid_to_str(workflow_id)}, {"$set": kwargs}
        )
        return await self.get_workflow_by_id(workflow_id)

    async def delete_workflow(self, workflow_id: uuid.UUID) -> None:
        await self._db.workflows.delete_one({"_id": _uuid_to_str(workflow_id)})

    # ------------------------------------------------------------------
    # Repository
    # ------------------------------------------------------------------

    async def create_repository(self, **kwargs: Any) -> _MongoDoc:
        if "id" not in kwargs:
            kwargs["id"] = _uuid_to_str(uuid.uuid4())
        else:
            kwargs["id"] = _uuid_to_str(kwargs["id"])
        kwargs.setdefault("company_id", "default")
        for uuid_field in ("workflow_id",):
            if uuid_field in kwargs and isinstance(kwargs[uuid_field], uuid.UUID):
                kwargs[uuid_field] = _uuid_to_str(kwargs[uuid_field])
        kwargs.setdefault("state_path", ".minder")
        kwargs.setdefault("context_snapshot", {})
        kwargs.setdefault("relationships", {})
        kwargs.setdefault("created_at", _now())
        kwargs.setdefault("updated_at", _now())
        kwargs["_id"] = kwargs.pop("id")
        await self._db.repositories.insert_one(kwargs)
        return _to_doc(kwargs)

    async def get_repository_by_id(self, repo_id: uuid.UUID) -> _MongoDoc | None:
        doc = await self._db.repositories.find_one({"_id": _uuid_to_str(repo_id)})
        return _to_doc(doc) if doc else None

    async def get_repository_by_name(self, repo_name: str) -> _MongoDoc | None:
        doc = await self._db.repositories.find_one({"repo_name": repo_name})
        return _to_doc(doc) if doc else None

    async def list_repositories(self) -> list[_MongoDoc]:
        cursor = self._db.repositories.find()
        return [_to_doc(doc) async for doc in cursor]

    async def update_repository(self, repo_id: uuid.UUID, **kwargs: Any) -> _MongoDoc | None:
        if not kwargs:
            return await self.get_repository_by_id(repo_id)
        kwargs["updated_at"] = _now()
        await self._db.repositories.update_one(
            {"_id": _uuid_to_str(repo_id)}, {"$set": kwargs}
        )
        return await self.get_repository_by_id(repo_id)

    async def delete_repository(self, repo_id: uuid.UUID) -> None:
        await self._db.repositories.delete_one({"_id": _uuid_to_str(repo_id)})

    # ------------------------------------------------------------------
    # RepositoryWorkflowState
    # ------------------------------------------------------------------

    async def create_workflow_state(self, **kwargs: Any) -> _MongoDoc:
        if "id" not in kwargs:
            kwargs["id"] = _uuid_to_str(uuid.uuid4())
        else:
            kwargs["id"] = _uuid_to_str(kwargs["id"])
        for uuid_field in ("repo_id", "session_id"):
            if uuid_field in kwargs and isinstance(kwargs[uuid_field], uuid.UUID):
                kwargs[uuid_field] = _uuid_to_str(kwargs[uuid_field])
        kwargs.setdefault("completed_steps", [])
        kwargs.setdefault("blocked_by", [])
        kwargs.setdefault("artifacts", {})
        kwargs.setdefault("next_step", None)
        kwargs.setdefault("updated_at", _now())
        kwargs["_id"] = kwargs.pop("id")
        await self._db.repository_workflow_states.insert_one(kwargs)
        return _to_doc(kwargs)

    async def get_workflow_state_by_id(self, state_id: uuid.UUID) -> _MongoDoc | None:
        doc = await self._db.repository_workflow_states.find_one(
            {"_id": _uuid_to_str(state_id)}
        )
        return _to_doc(doc) if doc else None

    async def get_workflow_state_by_repo(self, repo_id: uuid.UUID) -> _MongoDoc | None:
        doc = await self._db.repository_workflow_states.find_one(
            {"repo_id": _uuid_to_str(repo_id)}
        )
        return _to_doc(doc) if doc else None

    async def update_workflow_state(
        self, state_id: uuid.UUID, **kwargs: Any
    ) -> _MongoDoc | None:
        if not kwargs:
            return await self.get_workflow_state_by_id(state_id)
        kwargs["updated_at"] = _now()
        await self._db.repository_workflow_states.update_one(
            {"_id": _uuid_to_str(state_id)}, {"$set": kwargs}
        )
        return await self.get_workflow_state_by_id(state_id)

    async def delete_workflow_state(self, state_id: uuid.UUID) -> None:
        await self._db.repository_workflow_states.delete_one(
            {"_id": _uuid_to_str(state_id)}
        )

    # ------------------------------------------------------------------
    # Document (metadata — not vector store)
    # ------------------------------------------------------------------

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
    ) -> _MongoDoc:
        doc_id = _uuid_to_str(uuid.uuid4())
        document: dict[str, Any] = {
            "_id": doc_id,
            "title": title,
            "content": content,
            "doc_type": doc_type,
            "source_path": source_path,
            "project": project,
            "chunks": chunks or {},
            "embedding": embedding,
            "created_at": _now(),
            "updated_at": _now(),
        }
        await self._db.documents.insert_one(document)
        return _to_doc(document)

    async def get_document_by_path(
        self, source_path: str, *, project: str | None = None
    ) -> _MongoDoc | None:
        query: dict[str, Any] = {"source_path": source_path}
        if project is not None:
            query["project"] = project
        doc = await self._db.documents.find_one(query)
        return _to_doc(doc) if doc else None

    async def list_documents(self, project: str | None = None) -> list[_MongoDoc]:
        query: dict[str, Any] = {}
        if project is not None:
            query["project"] = project
        cursor = self._db.documents.find(query)
        return [_to_doc(doc) async for doc in cursor]

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
    ) -> _MongoDoc:
        existing = await self.get_document_by_path(source_path, project=project)
        if existing is None:
            return await self.create_document(
                title=title,
                content=content,
                doc_type=doc_type,
                source_path=source_path,
                project=project,
                chunks=chunks,
                embedding=embedding,
            )
        await self._db.documents.update_one(
            {"_id": _uuid_to_str(existing.id)},
            {
                "$set": {
                    "title": title,
                    "content": content,
                    "doc_type": doc_type,
                    "chunks": chunks or {},
                    "embedding": embedding,
                    "project": project,
                    "updated_at": _now(),
                }
            },
        )
        updated = await self._db.documents.find_one({"_id": _uuid_to_str(existing.id)})
        return _to_doc(updated)  # type: ignore[arg-type]

    async def delete_documents_not_in_paths(
        self, *, project: str, keep_paths: set[str]
    ) -> None:
        query: dict[str, Any] = {"project": project}
        if keep_paths:
            query["source_path"] = {"$nin": list(keep_paths)}
        await self._db.documents.delete_many(query)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    async def create_history(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        reasoning_trace: str | None = None,
        tool_calls: dict[str, Any] | None = None,
        tokens_used: int = 0,
        latency_ms: int = 0,
    ) -> _MongoDoc:
        doc_id = _uuid_to_str(uuid.uuid4())
        document: dict[str, Any] = {
            "_id": doc_id,
            "session_id": _uuid_to_str(session_id),
            "role": role,
            "content": content,
            "reasoning_trace": reasoning_trace,
            "tool_calls": tool_calls or {},
            "tokens_used": tokens_used,
            "latency_ms": latency_ms,
            "created_at": _now(),
        }
        await self._db.history.insert_one(document)
        return _to_doc(document)

    async def list_history_for_session(self, session_id: uuid.UUID) -> list[_MongoDoc]:
        cursor = self._db.history.find({"session_id": _uuid_to_str(session_id)})
        return [_to_doc(doc) async for doc in cursor]

    async def list_history_for_user(self, user_id: uuid.UUID) -> list[_MongoDoc]:
        # Get all session IDs for this user, then get history for those sessions
        user_id_str = _uuid_to_str(user_id)
        session_cursor = self._db.sessions.find(
            {"user_id": user_id_str}, {"_id": 1}
        )
        session_ids = [doc["_id"] async for doc in session_cursor]
        if not session_ids:
            return []
        cursor = self._db.history.find({"session_id": {"$in": session_ids}})
        return [_to_doc(doc) async for doc in cursor]

    # ------------------------------------------------------------------
    # Error
    # ------------------------------------------------------------------

    async def create_error(
        self,
        error_code: str,
        error_message: str,
        stack_trace: str | None = None,
        context: dict[str, Any] | None = None,
        resolution: str | None = None,
        embedding: list[float] | None = None,
        resolved: bool = False,
    ) -> _MongoDoc:
        doc_id = _uuid_to_str(uuid.uuid4())
        document: dict[str, Any] = {
            "_id": doc_id,
            "error_code": error_code,
            "error_message": error_message,
            "stack_trace": stack_trace,
            "context": context or {},
            "resolution": resolution,
            "embedding": embedding,
            "resolved": resolved,
            "created_at": _now(),
        }
        await self._db.errors.insert_one(document)
        return _to_doc(document)

    async def list_errors(self) -> list[_MongoDoc]:
        cursor = self._db.errors.find()
        return [_to_doc(doc) async for doc in cursor]

    async def search_errors(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Simple TF-based error search (same as SQLite adapter for now)."""
        rows = await self.list_errors()
        query_vector = self._text_vector(query)
        ranked: list[dict[str, Any]] = []
        for row in rows:
            text = f"{row.error_code} {row.error_message} {row.context}"
            score = self._cosine_similarity(query_vector, self._text_vector(text))
            ranked.append(
                {
                    "id": row.id,
                    "error_code": row.error_code,
                    "error_message": row.error_message,
                    "resolution": row.resolution,
                    "score": round(score, 4),
                }
            )
        ranked.sort(key=lambda item: cast(float, item["score"]), reverse=True)
        return ranked[:limit]

    @staticmethod
    def _text_vector(text: str) -> Counter[str]:
        return Counter(token for token in text.lower().split() if len(token) > 2)

    @staticmethod
    def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0
        numerator = sum(left[key] * right[key] for key in left.keys() & right.keys())
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)
