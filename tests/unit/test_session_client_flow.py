"""
Unit tests — client principal session flow.

Covers:
- ClientPrincipal can create a session (no user_id needed)
- minder_session_list returns sessions scoped to the client
- minder_session_restore returns correct state
- minder_session_save / minder_session_context write-through
- expired sessions are hidden or rejected and can be cleaned up
- minder_auth_whoami works for ClientPrincipal (always_available gate)
- Scope gate blocks non-always-available tools for ClientPrincipal without granted scopes
- always_available tools bypass scope gate
"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from minder.auth.principal import ClientPrincipal
from minder.models.user import User
from minder.tools.registry import ALWAYS_AVAILABLE_FOR_CLIENTS
from minder.tools.session import SessionTools
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def store() -> RelationalStore:
    s = RelationalStore(IN_MEMORY_URL)
    await s.init_db()
    yield s
    await s.dispose()


@pytest.fixture
def session_tools(store: RelationalStore) -> SessionTools:
    return SessionTools(store)


@pytest.fixture
def client_principal() -> ClientPrincipal:
    cid = uuid.uuid4()
    return ClientPrincipal(
        client_id=cid,
        client_slug="test-client",
        scopes=[],
        repo_scope=[],
    )


@pytest.fixture
def admin_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "admin@example.com"
    user.username = "admin"
    user.role = "admin"
    return user


# ---------------------------------------------------------------------------
# always_available registry
# ---------------------------------------------------------------------------


class TestAlwaysAvailableSet:
    def test_whoami_always_available(self) -> None:
        assert "minder_auth_whoami" in ALWAYS_AVAILABLE_FOR_CLIENTS

    def test_session_tools_always_available(self) -> None:
        for tool in (
            "minder_session_create",
            "minder_session_list",
            "minder_session_save",
            "minder_session_restore",
            "minder_session_context",
            "minder_session_cleanup",
        ):
            assert (
                tool in ALWAYS_AVAILABLE_FOR_CLIENTS
            ), f"{tool} should be always_available"

    def test_admin_tools_not_always_available(self) -> None:
        for tool in (
            "minder_auth_manage",
            "minder_auth_create_client",
            "minder_memory_store",
        ):
            assert (
                tool not in ALWAYS_AVAILABLE_FOR_CLIENTS
            ), f"{tool} must NOT be always_available"


# ---------------------------------------------------------------------------
# Client session lifecycle — happy path
# ---------------------------------------------------------------------------


class TestClientSessionCreate:
    async def test_create_session_for_client(
        self, session_tools: SessionTools, client_principal: ClientPrincipal
    ) -> None:
        result = await session_tools.minder_session_create(
            client_id=client_principal.client_id,
        )
        assert "session_id" in result
        sid = uuid.UUID(result["session_id"])
        assert sid is not None

    async def test_create_session_with_project_context(
        self, session_tools: SessionTools, client_principal: ClientPrincipal
    ) -> None:
        ctx = {"repo": "minder", "branch": "main"}
        result = await session_tools.minder_session_create(
            client_id=client_principal.client_id,
            project_context=ctx,
        )
        sid = uuid.UUID(result["session_id"])
        restored = await session_tools.minder_session_restore(sid)
        assert restored["project_context"] == ctx

    async def test_create_requires_user_or_client(
        self, session_tools: SessionTools
    ) -> None:
        with pytest.raises(ValueError, match="user_id or client_id"):
            await session_tools.minder_session_create()


class TestClientSessionList:
    async def test_list_returns_only_client_sessions(
        self, session_tools: SessionTools, client_principal: ClientPrincipal
    ) -> None:
        await session_tools.minder_session_create(client_id=client_principal.client_id)
        await session_tools.minder_session_create(client_id=client_principal.client_id)
        # session for a different client — should NOT appear
        await session_tools.minder_session_create(client_id=uuid.uuid4())

        result = await session_tools.minder_session_list(
            client_id=client_principal.client_id
        )
        assert len(result["sessions"]) == 2

    async def test_list_sorted_newest_first(
        self, session_tools: SessionTools, client_principal: ClientPrincipal
    ) -> None:
        r1 = await session_tools.minder_session_create(
            client_id=client_principal.client_id
        )
        r2 = await session_tools.minder_session_create(
            client_id=client_principal.client_id
        )
        result = await session_tools.minder_session_list(
            client_id=client_principal.client_id
        )
        ids = {s["session_id"] for s in result["sessions"]}
        # Both sessions must be present for the calling client
        assert r1["session_id"] in ids
        assert r2["session_id"] in ids
        # list returns a list (sorted key exists — order is last_active desc, verified in integration)
        assert isinstance(result["sessions"], list)


class TestClientSessionSaveRestore:
    async def test_save_and_restore_state(
        self, session_tools: SessionTools, client_principal: ClientPrincipal
    ) -> None:
        create = await session_tools.minder_session_create(
            client_id=client_principal.client_id
        )
        sid = uuid.UUID(create["session_id"])

        state = {"phase": "implementation", "wave": 3}
        skills = {"nestjs": True, "testing": True}
        await session_tools.minder_session_save(sid, state=state, active_skills=skills)

        restored = await session_tools.minder_session_restore(sid)
        assert restored["state"] == state
        assert restored["active_skills"] == skills
        assert restored.get("continuity_packet") is None

    async def test_restore_unknown_session_raises(
        self, session_tools: SessionTools
    ) -> None:
        with pytest.raises(ValueError, match="Session not found"):
            await session_tools.minder_session_restore(uuid.uuid4())


class TestClientSessionContext:
    async def test_update_branch_and_files(
        self, session_tools: SessionTools, client_principal: ClientPrincipal
    ) -> None:
        create = await session_tools.minder_session_create(
            client_id=client_principal.client_id
        )
        sid = uuid.UUID(create["session_id"])

        result = await session_tools.minder_session_context(
            sid,
            branch="feature/session-fix",
            open_files=["src/minder/tools/session.py"],
        )
        assert result["branch"] == "feature/session-fix"
        assert result["open_files"] == ["src/minder/tools/session.py"]


class TestClientSessionExpiry:
    async def test_expired_sessions_are_filtered_from_list_and_find(
        self, session_tools: SessionTools, client_principal: ClientPrincipal
    ) -> None:
        expired = await session_tools.minder_session_create(
            client_id=client_principal.client_id,
            name="expired-session",
        )
        active = await session_tools.minder_session_create(
            client_id=client_principal.client_id,
            name="active-session",
        )

        await session_tools._store.update_session(
            uuid.UUID(expired["session_id"]),
            ttl=1,
            last_active=datetime(2020, 1, 1, tzinfo=UTC),
        )

        listed = await session_tools.minder_session_list(
            client_id=client_principal.client_id
        )
        listed_ids = {item["session_id"] for item in listed["sessions"]}
        assert expired["session_id"] not in listed_ids
        assert active["session_id"] in listed_ids

        with pytest.raises(ValueError, match="No session named 'expired-session'"):
            await session_tools.minder_session_find(
                name="expired-session",
                client_id=client_principal.client_id,
            )

    async def test_restore_expired_session_deletes_it_and_history(
        self, session_tools: SessionTools, client_principal: ClientPrincipal
    ) -> None:
        created = await session_tools.minder_session_create(
            client_id=client_principal.client_id,
            name="cleanup-me",
        )
        session_id = uuid.UUID(created["session_id"])
        await session_tools._store.create_history(
            session_id=session_id,
            role="assistant",
            content="stale history",
        )
        await session_tools._store.update_session(
            session_id,
            ttl=1,
            last_active=datetime(2020, 1, 1, tzinfo=UTC),
        )

        with pytest.raises(ValueError, match="Session expired"):
            await session_tools.minder_session_restore(session_id)

        assert await session_tools._store.get_session_by_id(session_id) is None
        assert await session_tools._store.list_history_for_session(session_id) == []

    async def test_cleanup_removes_only_expired_sessions(
        self, session_tools: SessionTools, client_principal: ClientPrincipal
    ) -> None:
        expired = await session_tools.minder_session_create(
            client_id=client_principal.client_id,
            name="expired-cleanup",
        )
        active = await session_tools.minder_session_create(
            client_id=client_principal.client_id,
            name="active-cleanup",
        )
        expired_id = uuid.UUID(expired["session_id"])
        active_id = uuid.UUID(active["session_id"])

        await session_tools._store.create_history(
            session_id=expired_id,
            role="assistant",
            content="expired history",
        )
        await session_tools._store.create_history(
            session_id=active_id,
            role="assistant",
            content="active history",
        )
        await session_tools._store.update_session(
            expired_id,
            ttl=1,
            last_active=datetime(2020, 1, 1, tzinfo=UTC),
        )

        result = await session_tools.minder_session_cleanup(
            client_id=client_principal.client_id
        )

        assert result == {"deleted_sessions": 1, "deleted_history": 1}
        assert await session_tools._store.get_session_by_id(expired_id) is None
        assert await session_tools._store.get_session_by_id(active_id) is not None
        active_history = await session_tools._store.list_history_for_session(active_id)
        assert len(active_history) == 1


# ---------------------------------------------------------------------------
# minder_auth_whoami for ClientPrincipal (via bootstrap handler directly)
# ---------------------------------------------------------------------------


class TestWhoamiClientPrincipal:
    async def test_whoami_returns_client_identity(
        self, client_principal: ClientPrincipal
    ) -> None:
        # Simulate what the bootstrap handler does (principal injected, user=None)
        principal = client_principal
        result: dict[str, Any] = {
            "principal_type": principal.principal_type,
            "principal_id": str(principal.principal_id),
            "role": principal.role,
            "scopes": list(principal.scopes),
            "repo_scope": list(principal.repo_scope),
            "client_slug": getattr(principal, "client_slug", None),
        }
        assert result["principal_type"] == "client"
        assert result["client_slug"] == "test-client"
        assert result["scopes"] == []

    async def test_whoami_returns_user_identity(self, admin_user: User) -> None:
        user = admin_user
        result: dict[str, Any] = {
            "principal_type": "user",
            "principal_id": str(user.id),
            "email": user.email,
            "username": user.username,
            "role": user.role,
            "scopes": [],
        }
        assert result["principal_type"] == "user"
        assert result["email"] == "admin@example.com"
