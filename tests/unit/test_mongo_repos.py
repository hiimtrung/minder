"""
Unit tests for MongoDB Operational Store.

These tests use a real Motor client against a mocked or in-memory-style
MongoDB connection. Since Motor doesn't have a built-in mock, we test
the MongoOperationalStore with a real MongoDB if available, or skip
gracefully with a pytest marker.

For CI, these tests will run when MongoDB is in Docker Compose.
For local dev, they can be skipped with: pytest -m "not requires_mongodb"
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

# -----------------------------------------------------------------------
# Skip guard: only run when MongoDB is reachable
# -----------------------------------------------------------------------

try:
    from motor.motor_asyncio import AsyncIOMotorClient

    _motor_available = True
except ImportError:
    _motor_available = False

requires_mongodb = pytest.mark.skipif(
    not _motor_available,
    reason="motor not installed",
)


async def _mongo_reachable() -> bool:
    """Quick ping to check if MongoDB is running locally."""
    if not _motor_available:
        return False
    try:
        client: AsyncIOMotorClient = AsyncIOMotorClient(  # type: ignore[type-arg]
            "mongodb://localhost:27017",
            serverSelectionTimeoutMS=1000,
        )
        await client.admin.command("ping")
        client.close()
        return True
    except Exception:
        return False


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------


@pytest_asyncio.fixture
async def mongo_store():
    """Create a MongoOperationalStore against a test database."""
    from minder.store.mongodb.client import MongoClient
    from minder.store.mongodb.operational_store import MongoOperationalStore

    reachable = await _mongo_reachable()
    if not reachable:
        pytest.skip("MongoDB not reachable at localhost:27017")

    test_db = f"minder_test_{uuid.uuid4().hex[:8]}"
    client = MongoClient(
        uri="mongodb://localhost:27017",
        database=test_db,
    )
    store = MongoOperationalStore(client)
    await store.init_db()
    yield store
    # Cleanup: drop the test database
    await client.db.client.drop_database(test_db)
    await store.dispose()


# -----------------------------------------------------------------------
# User CRUD Tests
# -----------------------------------------------------------------------


@requires_mongodb
class TestMongoUserRepository:
    @pytest.mark.asyncio
    async def test_create_user(self, mongo_store: object) -> None:
        from minder.store.mongodb.operational_store import MongoOperationalStore

        store: MongoOperationalStore = mongo_store  # type: ignore[assignment]
        user = await store.create_user(
            email="test@example.com",
            username="testuser",
            display_name="Test User",
            api_key_hash="hash123",
            role="admin",
        )
        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.role == "admin"
        assert isinstance(user.id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_get_user_by_email(self, mongo_store: object) -> None:
        from minder.store.mongodb.operational_store import MongoOperationalStore

        store: MongoOperationalStore = mongo_store  # type: ignore[assignment]
        await store.create_user(
            email="find@example.com",
            username="finduser",
            display_name="Find User",
            api_key_hash="hash456",
            role="member",
        )
        found = await store.get_user_by_email("find@example.com")
        assert found is not None
        assert found.username == "finduser"

    @pytest.mark.asyncio
    async def test_update_user(self, mongo_store: object) -> None:
        from minder.store.mongodb.operational_store import MongoOperationalStore

        store: MongoOperationalStore = mongo_store  # type: ignore[assignment]
        user = await store.create_user(
            email="update@example.com",
            username="updateuser",
            display_name="Before Update",
            api_key_hash="hash789",
            role="member",
        )
        updated = await store.update_user(user.id, display_name="After Update")
        assert updated is not None
        assert updated.display_name == "After Update"

    @pytest.mark.asyncio
    async def test_delete_user(self, mongo_store: object) -> None:
        from minder.store.mongodb.operational_store import MongoOperationalStore

        store: MongoOperationalStore = mongo_store  # type: ignore[assignment]
        user = await store.create_user(
            email="delete@example.com",
            username="deleteuser",
            display_name="Delete Me",
            api_key_hash="hashabc",
            role="member",
        )
        await store.delete_user(user.id)
        gone = await store.get_user_by_id(user.id)
        assert gone is None

    @pytest.mark.asyncio
    async def test_list_users(self, mongo_store: object) -> None:
        from minder.store.mongodb.operational_store import MongoOperationalStore

        store: MongoOperationalStore = mongo_store  # type: ignore[assignment]
        await store.create_user(
            email="list1@example.com",
            username="listuser1",
            display_name="List 1",
            api_key_hash="h1",
            role="member",
        )
        await store.create_user(
            email="list2@example.com",
            username="listuser2",
            display_name="List 2",
            api_key_hash="h2",
            role="member",
            is_active=False,
        )
        active = await store.list_users(active_only=True)
        all_users = await store.list_users(active_only=False)
        assert len(active) == 1
        assert len(all_users) == 2


# -----------------------------------------------------------------------
# Skill CRUD Tests
# -----------------------------------------------------------------------


@requires_mongodb
class TestMongoSkillRepository:
    @pytest.mark.asyncio
    async def test_create_and_list_skills(self, mongo_store: object) -> None:
        from minder.store.mongodb.operational_store import MongoOperationalStore

        store: MongoOperationalStore = mongo_store  # type: ignore[assignment]
        skill = await store.create_skill(
            title="Python debugging",
            content="Use pdb for interactive debugging",
            language="python",
            tags=["debug", "python"],
        )
        assert skill.title == "Python debugging"
        skills = await store.list_skills()
        assert len(skills) == 1

    @pytest.mark.asyncio
    async def test_delete_skill(self, mongo_store: object) -> None:
        from minder.store.mongodb.operational_store import MongoOperationalStore

        store: MongoOperationalStore = mongo_store  # type: ignore[assignment]
        skill = await store.create_skill(
            title="Temp Skill",
            content="content",
            language="python",
        )
        await store.delete_skill(skill.id)
        gone = await store.get_skill_by_id(skill.id)
        assert gone is None


# -----------------------------------------------------------------------
# Session CRUD Tests
# -----------------------------------------------------------------------


@requires_mongodb
class TestMongoSessionRepository:
    @pytest.mark.asyncio
    async def test_session_lifecycle(self, mongo_store: object) -> None:
        from minder.store.mongodb.operational_store import MongoOperationalStore

        store: MongoOperationalStore = mongo_store  # type: ignore[assignment]
        user_id = uuid.uuid4()
        session = await store.create_session(user_id=user_id)
        assert session.user_id == user_id

        found = await store.get_session_by_id(session.id)
        assert found is not None

        updated = await store.update_session(session.id, state={"step": "coding"})
        assert updated is not None
        assert updated.state == {"step": "coding"}

        user_sessions = await store.get_sessions_by_user(user_id)
        assert len(user_sessions) == 1

        await store.delete_session(session.id)
        gone = await store.get_session_by_id(session.id)
        assert gone is None


# -----------------------------------------------------------------------
# Document CRUD Tests
# -----------------------------------------------------------------------


@requires_mongodb
class TestMongoDocumentRepository:
    @pytest.mark.asyncio
    async def test_document_upsert(self, mongo_store: object) -> None:
        from minder.store.mongodb.operational_store import MongoOperationalStore

        store: MongoOperationalStore = mongo_store  # type: ignore[assignment]
        doc = await store.upsert_document(
            title="README",
            content="# Hello",
            doc_type="markdown",
            source_path="/project/README.md",
            project="test-project",
        )
        assert doc.title == "README"

        # Upsert same path → update
        updated = await store.upsert_document(
            title="README v2",
            content="# Updated",
            doc_type="markdown",
            source_path="/project/README.md",
            project="test-project",
        )
        assert updated.title == "README v2"

        docs = await store.list_documents(project="test-project")
        assert len(docs) == 1

    @pytest.mark.asyncio
    async def test_delete_documents_not_in_paths(self, mongo_store: object) -> None:
        from minder.store.mongodb.operational_store import MongoOperationalStore

        store: MongoOperationalStore = mongo_store  # type: ignore[assignment]
        await store.create_document(
            title="Keep",
            content="keep",
            doc_type="code",
            source_path="/keep.py",
            project="p",
        )
        await store.create_document(
            title="Remove",
            content="remove",
            doc_type="code",
            source_path="/remove.py",
            project="p",
        )
        await store.delete_documents_not_in_paths(
            project="p", keep_paths={"/keep.py"}
        )
        remaining = await store.list_documents(project="p")
        assert len(remaining) == 1
        assert remaining[0].source_path == "/keep.py"


# -----------------------------------------------------------------------
# Error & History Tests
# -----------------------------------------------------------------------


@requires_mongodb
class TestMongoErrorAndHistory:
    @pytest.mark.asyncio
    async def test_error_create_and_search(self, mongo_store: object) -> None:
        from minder.store.mongodb.operational_store import MongoOperationalStore

        store: MongoOperationalStore = mongo_store  # type: ignore[assignment]
        error = await store.create_error(
            error_code="BIZ_USER_NOT_FOUND",
            error_message="User with this ID does not exist",
        )
        assert error.error_code == "BIZ_USER_NOT_FOUND"

        results = await store.search_errors("user not found", limit=5)
        assert len(results) >= 1
        assert results[0]["error_code"] == "BIZ_USER_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_history_lifecycle(self, mongo_store: object) -> None:
        from minder.store.mongodb.operational_store import MongoOperationalStore

        store: MongoOperationalStore = mongo_store  # type: ignore[assignment]
        session_id = uuid.uuid4()
        history = await store.create_history(
            session_id=session_id,
            role="user",
            content="How do I fix this bug?",
        )
        assert history.role == "user"

        entries = await store.list_history_for_session(session_id)
        assert len(entries) == 1
