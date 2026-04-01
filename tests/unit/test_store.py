"""
Unit tests for RelationalStore using in-memory SQLite.
Covers: User, Session, Workflow, Repository, RepositoryWorkflowState CRUD.
"""

import uuid

import pytest

from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def store() -> RelationalStore:
    s = RelationalStore(IN_MEMORY_URL)
    await s.init_db()
    yield s
    await s.dispose()


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


class TestUserCRUD:
    async def test_create_and_get_by_id(self, store: RelationalStore) -> None:
        uid = uuid.uuid4()
        user = await store.create_user(
            id=uid,
            email="alice@example.com",
            username="alice",
            display_name="Alice",
            api_key_hash="hash_alice",
            role="member",
            is_active=True,
            settings={},
        )
        assert user.id == uid
        assert user.email == "alice@example.com"

        fetched = await store.get_user_by_id(uid)
        assert fetched is not None
        assert fetched.username == "alice"

    async def test_get_by_email(self, store: RelationalStore) -> None:
        await store.create_user(
            id=uuid.uuid4(),
            email="bob@example.com",
            username="bob",
            display_name="Bob",
            api_key_hash="hash_bob",
            role="member",
            is_active=True,
            settings={},
        )
        user = await store.get_user_by_email("bob@example.com")
        assert user is not None
        assert user.username == "bob"

    async def test_get_by_username(self, store: RelationalStore) -> None:
        await store.create_user(
            id=uuid.uuid4(),
            email="carol@example.com",
            username="carol",
            display_name="Carol",
            api_key_hash="hash_carol",
            role="readonly",
            is_active=True,
            settings={},
        )
        user = await store.get_user_by_username("carol")
        assert user is not None
        assert user.email == "carol@example.com"

    async def test_get_nonexistent_returns_none(self, store: RelationalStore) -> None:
        result = await store.get_user_by_id(uuid.uuid4())
        assert result is None

    async def test_update_user(self, store: RelationalStore) -> None:
        uid = uuid.uuid4()
        await store.create_user(
            id=uid,
            email="dave@example.com",
            username="dave",
            display_name="Dave",
            api_key_hash="hash_dave",
            role="member",
            is_active=True,
            settings={},
        )
        updated = await store.update_user(uid, display_name="David")
        assert updated is not None
        assert updated.display_name == "David"

    async def test_list_users_active_only(self, store: RelationalStore) -> None:
        await store.create_user(
            id=uuid.uuid4(),
            email="active@example.com",
            username="active_user",
            display_name="Active",
            api_key_hash="h1",
            role="member",
            is_active=True,
            settings={},
        )
        await store.create_user(
            id=uuid.uuid4(),
            email="inactive@example.com",
            username="inactive_user",
            display_name="Inactive",
            api_key_hash="h2",
            role="member",
            is_active=False,
            settings={},
        )
        active = await store.list_users(active_only=True)
        emails = [u.email for u in active]
        assert "active@example.com" in emails
        assert "inactive@example.com" not in emails

    async def test_delete_user(self, store: RelationalStore) -> None:
        uid = uuid.uuid4()
        await store.create_user(
            id=uid,
            email="eve@example.com",
            username="eve",
            display_name="Eve",
            api_key_hash="hash_eve",
            role="admin",
            is_active=True,
            settings={},
        )
        await store.delete_user(uid)
        assert await store.get_user_by_id(uid) is None


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


class TestSessionCRUD:
    async def test_create_and_get_session(self, store: RelationalStore) -> None:
        user_id = uuid.uuid4()
        sid = uuid.uuid4()
        sess = await store.create_session(
            id=sid,
            user_id=user_id,
            project_context={},
            active_skills={},
            state={},
            ttl=3600,
        )
        assert sess.id == sid
        assert sess.user_id == user_id

        fetched = await store.get_session_by_id(sid)
        assert fetched is not None
        assert fetched.ttl == 3600

    async def test_get_sessions_by_user(self, store: RelationalStore) -> None:
        user_id = uuid.uuid4()
        for _ in range(3):
            await store.create_session(
                id=uuid.uuid4(),
                user_id=user_id,
                project_context={},
                active_skills={},
                state={},
                ttl=1800,
            )
        sessions = await store.get_sessions_by_user(user_id)
        assert len(sessions) == 3

    async def test_update_and_delete_session(self, store: RelationalStore) -> None:
        sid = uuid.uuid4()
        await store.create_session(
            id=sid,
            user_id=uuid.uuid4(),
            project_context={},
            active_skills={},
            state={},
            ttl=60,
        )
        updated = await store.update_session(sid, ttl=7200)
        assert updated is not None
        assert updated.ttl == 7200

        await store.delete_session(sid)
        assert await store.get_session_by_id(sid) is None


# ---------------------------------------------------------------------------
# Workflow CRUD
# ---------------------------------------------------------------------------


class TestWorkflowCRUD:
    async def test_create_and_get_workflow(self, store: RelationalStore) -> None:
        wf = await store.create_workflow(
            id=uuid.uuid4(),
            name="tdd",
            version=1,
            steps=[{"name": "test_writing"}, {"name": "implementation"}],
            policies={"block_step_skips": True},
            default_for_repo=True,
        )
        assert wf.name == "tdd"

        by_name = await store.get_workflow_by_name("tdd")
        assert by_name is not None
        assert by_name.default_for_repo is True

    async def test_list_workflows(self, store: RelationalStore) -> None:
        for name in ("tdd", "review", "deploy"):
            await store.create_workflow(
                id=uuid.uuid4(),
                name=name,
                version=1,
                steps=[],
                policies={},
                default_for_repo=False,
            )
        workflows = await store.list_workflows()
        assert len(workflows) == 3

    async def test_update_and_delete_workflow(self, store: RelationalStore) -> None:
        wid = uuid.uuid4()
        await store.create_workflow(
            id=wid,
            name="old_name",
            version=1,
            steps=[],
            policies={},
            default_for_repo=False,
        )
        updated = await store.update_workflow(wid, version=2)
        assert updated is not None
        assert updated.version == 2

        await store.delete_workflow(wid)
        assert await store.get_workflow_by_id(wid) is None


# ---------------------------------------------------------------------------
# Repository CRUD
# ---------------------------------------------------------------------------


class TestRepositoryCRUD:
    async def test_create_and_get_repository(self, store: RelationalStore) -> None:
        rid = uuid.uuid4()
        repo = await store.create_repository(
            id=rid,
            repo_name="my-service",
            repo_url="https://github.com/org/my-service",
            default_branch="main",
            state_path=".minder",
            context_snapshot={},
            relationships={},
        )
        assert repo.repo_name == "my-service"

        by_name = await store.get_repository_by_name("my-service")
        assert by_name is not None
        assert str(by_name.id) == str(rid)

    async def test_update_repository(self, store: RelationalStore) -> None:
        rid = uuid.uuid4()
        await store.create_repository(
            id=rid,
            repo_name="svc",
            repo_url="https://github.com/org/svc",
            default_branch="main",
            state_path=".minder",
            context_snapshot={},
            relationships={},
        )
        wf_id = uuid.uuid4()
        updated = await store.update_repository(rid, workflow_id=wf_id)
        assert updated is not None
        assert updated.workflow_id == wf_id

    async def test_list_and_delete_repository(self, store: RelationalStore) -> None:
        for i in range(2):
            await store.create_repository(
                id=uuid.uuid4(),
                repo_name=f"repo-{i}",
                repo_url=f"https://github.com/org/repo-{i}",
                default_branch="main",
                state_path=".minder",
                context_snapshot={},
                relationships={},
            )
        repos = await store.list_repositories()
        assert len(repos) == 2

        await store.delete_repository(repos[0].id)
        assert len(await store.list_repositories()) == 1


# ---------------------------------------------------------------------------
# RepositoryWorkflowState CRUD
# ---------------------------------------------------------------------------


class TestWorkflowStateCRUD:
    async def test_create_and_get_by_repo(self, store: RelationalStore) -> None:
        repo_id = uuid.uuid4()
        state = await store.create_workflow_state(
            id=uuid.uuid4(),
            repo_id=repo_id,
            current_step="test_writing",
            completed_steps=[],
            blocked_by=[],
            artifacts={},
        )
        assert state.current_step == "test_writing"

        fetched = await store.get_workflow_state_by_repo(repo_id)
        assert fetched is not None
        assert fetched.repo_id == repo_id

    async def test_update_workflow_state(self, store: RelationalStore) -> None:
        sid = uuid.uuid4()
        repo_id = uuid.uuid4()
        await store.create_workflow_state(
            id=sid,
            repo_id=repo_id,
            current_step="test_writing",
            completed_steps=[],
            blocked_by=[],
            artifacts={},
        )
        updated = await store.update_workflow_state(
            sid,
            current_step="implementation",
            completed_steps=["test_writing"],
        )
        assert updated is not None
        assert updated.current_step == "implementation"

    async def test_delete_workflow_state(self, store: RelationalStore) -> None:
        sid = uuid.uuid4()
        await store.create_workflow_state(
            id=sid,
            repo_id=uuid.uuid4(),
            current_step="review",
            completed_steps=["test_writing", "implementation"],
            blocked_by=[],
            artifacts={},
        )
        await store.delete_workflow_state(sid)
        assert await store.get_workflow_state_by_id(sid) is None
