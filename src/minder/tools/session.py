from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from minder.store.interfaces import IOperationalStore


class SessionTools:
    def __init__(self, store: IOperationalStore) -> None:
        self._store = store

    async def minder_session_create(
        self,
        *,
        user_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
        repo_id: uuid.UUID | None = None,
        project_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if user_id is None and client_id is None:
            raise ValueError("Either user_id or client_id must be provided")
        session = await self._store.create_session(
            id=uuid.uuid4(),
            user_id=user_id,
            client_id=client_id,
            repo_id=repo_id,
            project_context=project_context or {},
            active_skills={},
            state={},
            ttl=3600,
        )
        return {"session_id": str(session.id)}

    async def minder_session_list(
        self,
        *,
        user_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Return active sessions for the calling principal, newest first."""
        if client_id is not None:
            sessions = await self._store.get_sessions_by_client(client_id)
        elif user_id is not None:
            sessions = await self._store.get_sessions_by_user(user_id)
        else:
            raise ValueError("Either user_id or client_id must be provided")
        return {
            "sessions": [
                {
                    "session_id": str(s.id),
                    "repo_id": str(s.repo_id) if s.repo_id else None,
                    "project_context": s.project_context,
                    "last_active": s.last_active.isoformat(),
                    "created_at": s.created_at.isoformat(),
                }
                for s in sorted(sessions, key=lambda s: s.last_active, reverse=True)
            ]
        }

    async def minder_session_save(
        self,
        session_id: uuid.UUID,
        *,
        state: dict[str, Any] | None = None,
        active_skills: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = await self._store.update_session(
            session_id,
            state=state or {},
            active_skills=active_skills or {},
            last_active=datetime.now(UTC),
        )
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        return {
            "session_id": str(session.id),
            "state": session.state,
            "active_skills": session.active_skills,
        }

    async def minder_session_restore(self, session_id: uuid.UUID) -> dict[str, Any]:
        session = await self._store.get_session_by_id(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        return {
            "session_id": str(session.id),
            "state": session.state,
            "active_skills": session.active_skills,
            "project_context": session.project_context,
        }

    async def minder_session_context(
        self,
        session_id: uuid.UUID,
        *,
        branch: str,
        open_files: list[str],
    ) -> dict[str, Any]:
        session = await self._store.get_session_by_id(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        project_context = dict(session.project_context)
        project_context.update({"branch": branch, "open_files": open_files})
        updated = await self._store.update_session(session_id, project_context=project_context)
        if updated is None:
            raise ValueError(f"Session not found: {session_id}")
        return {
            "session_id": str(updated.id),
            "branch": branch,
            "open_files": open_files,
        }


    async def minder_session_save(
        self,
        session_id: uuid.UUID,
        *,
        state: dict[str, Any] | None = None,
        active_skills: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = await self._store.update_session(
            session_id,
            state=state or {},
            active_skills=active_skills or {},
            last_active=datetime.now(UTC),
        )
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        return {
            "session_id": str(session.id),
            "state": session.state,
            "active_skills": session.active_skills,
        }

    async def minder_session_restore(self, session_id: uuid.UUID) -> dict[str, Any]:
        session = await self._store.get_session_by_id(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        return {
            "session_id": str(session.id),
            "state": session.state,
            "active_skills": session.active_skills,
            "project_context": session.project_context,
        }

    async def minder_session_context(
        self,
        session_id: uuid.UUID,
        *,
        branch: str,
        open_files: list[str],
    ) -> dict[str, Any]:
        session = await self._store.get_session_by_id(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        project_context = dict(session.project_context)
        project_context.update({"branch": branch, "open_files": open_files})
        updated = await self._store.update_session(session_id, project_context=project_context)
        if updated is None:
            raise ValueError(f"Session not found: {session_id}")
        return {
            "session_id": str(updated.id),
            "branch": branch,
            "open_files": open_files,
        }
