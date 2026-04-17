"""Session Tools — MCP surface for per-client LLM context persistence.

Design rationale
----------------
A session is the server-side checkpoint for a single LLM work context.  It is
keyed by a **server-assigned UUID** but is *also* addressable by a human-readable
**name** so the same LLM can resume the exact session from any machine using the
same client API key:

  Machine A:  minder_session_create(name="omi-channel-phase5")
              → {session_id: "a1b2..."}
  Machine B:  minder_session_find(name="omi-channel-phase5")
              → {session_id: "a1b2...", state: {...}, ...}

The `session_id` UUID is returned in every response so the LLM can cache it in
its context for faster subsequent calls while the session is active.  After a
``/compact`` or machine switch the LLM calls ``minder_session_find`` with the
project name and immediately regains full context.

Access control
--------------
Sessions are owned by the creating principal (user or client).  The ``session_id``
UUID acts as a bearer token for ``save``/``restore``/``context`` operations — the
server validates existence but does not re-check ownership on every call.
``minder_session_find`` enforces ownership by filtering on the caller's
principal_id automatically.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from minder.continuity import build_continuity_brief, build_instruction_envelope
from minder.observability.metrics import record_continuity_packet
from minder.store.interfaces import IOperationalStore


class SessionTools:
    def __init__(self, store: IOperationalStore) -> None:
        self._store = store

    def _normalize_datetime(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _expires_at(self, session: Any) -> datetime | None:
        ttl = int(getattr(session, "ttl", 0) or 0)
        if ttl <= 0:
            return None
        base = self._normalize_datetime(
            getattr(session, "last_active", None)
            or getattr(session, "created_at", None)
        )
        if base is None:
            return None
        return base + timedelta(seconds=ttl)

    def _is_expired(self, session: Any, *, now: datetime | None = None) -> bool:
        expires_at = self._expires_at(session)
        if expires_at is None:
            return False
        reference_time = self._normalize_datetime(now) or datetime.now(UTC)
        return expires_at <= reference_time

    async def _cleanup_session(self, session_id: uuid.UUID) -> dict[str, int]:
        deleted_history = await self._store.delete_history_for_session(session_id)
        await self._store.delete_session(session_id)
        return {"deleted_sessions": 1, "deleted_history": deleted_history}

    async def _require_active_session(self, session_id: uuid.UUID) -> Any:
        session = await self._store.get_session_by_id(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        if self._is_expired(session):
            await self._cleanup_session(session_id)
            raise ValueError(f"Session expired: {session_id}")
        return session

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def minder_session_create(
        self,
        *,
        user_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
        name: str | None = None,
        repo_id: uuid.UUID | None = None,
        project_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new persisted session for the calling principal.

        One of ``user_id`` (human admin) or ``client_id`` (MCP client) must be
        provided.  ``name`` is an optional project slug — use a stable, memorable
        name so the session can be found again from any machine with the same
        client API key.  Example: ``"omi-channel-phase5-dev"``.
        """
        if user_id is None and client_id is None:
            raise ValueError("Either user_id or client_id must be provided")
        session = await self._store.create_session(
            id=uuid.uuid4(),
            user_id=user_id,
            client_id=client_id,
            name=name,
            repo_id=repo_id,
            project_context=project_context or {},
            active_skills={},
            state={},
            ttl=86400,  # 24 h — long enough for multi-day work continuity
        )
        return {
            "session_id": str(session.id),
            "name": session.name,
        }

    # ------------------------------------------------------------------
    # Find / list
    # ------------------------------------------------------------------

    async def minder_session_find(
        self,
        *,
        name: str,
        user_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Find a session by name for the calling principal.

        This is the primary **cross-environment recovery** entry point.  The LLM
        calls this on any machine using the same client API key and immediately
        recovers full session state without needing to remember the UUID.

        Returns the full session payload (same shape as ``minder_session_restore``)
        or raises ``ValueError`` if no matching session is found.
        """
        session = await self._store.find_session_by_name(
            name,
            user_id=user_id,
            client_id=client_id,
        )
        if session is not None and not self._is_expired(session):
            return {
                "session_id": str(session.id),
                "name": session.name,
                "state": session.state,
                "active_skills": session.active_skills,
                "project_context": session.project_context,
                "last_active": session.last_active.isoformat(),
            }
        raise ValueError(
            f"No session named '{name}' found for the current principal. "
            "Use minder_session_list to see all sessions or minder_session_create to start one."
        )

    async def minder_session_list(
        self,
        *,
        user_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Return all sessions for the calling principal, newest-first.

        Use this when you need to browse sessions or when you do not remember the
        session name.  Prefer ``minder_session_find`` when you know the name.
        """
        if client_id is not None:
            sessions = await self._store.get_sessions_by_client(client_id)
        elif user_id is not None:
            sessions = await self._store.get_sessions_by_user(user_id)
        else:
            raise ValueError("Either user_id or client_id must be provided")
        active_sessions = [
            session for session in sessions if not self._is_expired(session)
        ]
        return {
            "sessions": [
                {
                    "session_id": str(s.id),
                    "name": s.name,
                    "repo_id": str(s.repo_id) if s.repo_id else None,
                    "project_context": s.project_context,
                    "last_active": s.last_active.isoformat(),
                    "created_at": s.created_at.isoformat(),
                }
                for s in sorted(
                    active_sessions, key=lambda s: s.last_active, reverse=True
                )
            ]
        }

    # ------------------------------------------------------------------
    # Save / restore / context
    # ------------------------------------------------------------------

    async def minder_session_save(
        self,
        session_id: uuid.UUID,
        *,
        state: dict[str, Any] | None = None,
        active_skills: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist the LLM's current task state and active skill set.

        Call this after every significant wave of work so the context survives
        ``/compact``, machine switches, or unexpected session drops.  The ``state``
        dict should capture:

        - Current task description and phase
        - Key decisions made
        - Files modified / in progress
        - Next planned steps
        - Open questions / blockers
        """
        await self._require_active_session(session_id)
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
            "name": session.name,
            "state": session.state,
            "active_skills": session.active_skills,
        }

    async def minder_session_restore(self, session_id: uuid.UUID) -> dict[str, Any]:
        """Restore a session checkpoint by UUID.

        Use ``minder_session_find`` instead when you know the session name —
        it performs owner-scoped lookup and returns the same payload.
        """
        session = await self._require_active_session(session_id)

        continuity_packet: dict[str, Any] | None = None
        if session.repo_id is not None:
            repo = await self._store.get_repository_by_id(session.repo_id)
            workflow_state = await self._store.get_workflow_state_by_repo(
                session.repo_id
            )
            workflow = None
            if repo is not None and repo.workflow_id is not None:
                workflow = await self._store.get_workflow_by_id(repo.workflow_id)
            if workflow is not None and workflow_state is not None:
                continuity_packet = {
                    "instruction_envelope": build_instruction_envelope(
                        workflow=workflow,
                        workflow_state=workflow_state,
                    ),
                    "session_brief": build_continuity_brief(
                        session=session,
                        workflow_state=workflow_state,
                        workflow=workflow,
                    ),
                }

        payload = {
            "session_id": str(session.id),
            "name": session.name,
            "state": session.state,
            "active_skills": session.active_skills,
            "project_context": session.project_context,
        }
        if continuity_packet is not None:
            record_continuity_packet("session_restore")
            payload["continuity_packet"] = continuity_packet
        return payload

    async def minder_session_context(
        self,
        session_id: uuid.UUID,
        *,
        branch: str,
        open_files: list[str],
    ) -> dict[str, Any]:
        """Update the repository context for an existing session.

        Call after a branch switch or when the set of actively edited files
        changes so that future session restores include current context.
        """
        session = await self._require_active_session(session_id)
        project_context = dict(session.project_context)
        project_context.update({"branch": branch, "open_files": open_files})
        updated = await self._store.update_session(
            session_id, project_context=project_context
        )
        if updated is None:
            raise ValueError(f"Session not found: {session_id}")
        return {
            "session_id": str(updated.id),
            "name": updated.name,
            "branch": branch,
            "open_files": open_files,
        }

    async def minder_session_cleanup(
        self,
        *,
        user_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        if client_id is None and user_id is None:
            raise ValueError("Either user_id or client_id must be provided")
        return await self._store.cleanup_expired_sessions(
            user_id=user_id,
            client_id=client_id,
        )
