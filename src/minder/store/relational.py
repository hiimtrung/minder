"""
Relational Store — async SQLAlchemy CRUD for all domain entities.

Supports SQLite (dev, via aiosqlite) and PostgreSQL (prod, via asyncpg).
URL examples:
  SQLite  : sqlite+aiosqlite:///path/to/minder.db
  In-mem  : sqlite+aiosqlite:///:memory:
  Postgres: postgresql+asyncpg://user:pass@host/db
"""

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from minder.models import (
    Base,
    Document,
    Error,
    History,
    Repository,
    RepositoryWorkflowState,
    Rule,
    Session,
    Skill,
    User,
    Workflow,
)

_REGISTERED_MODELS = (
    Document,
    Error,
    History,
    Repository,
    RepositoryWorkflowState,
    Rule,
    Session,
    Skill,
    User,
    Workflow,
)


class RelationalStore:
    """Async SQLAlchemy store. Thread-safe; one instance per application."""

    def __init__(self, db_url: str, echo: bool = False) -> None:
        self._engine: AsyncEngine = create_async_engine(db_url, echo=echo)
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init_db(self) -> None:
        """Create all tables (idempotent)."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        """Dispose the engine connection pool."""
        await self._engine.dispose()

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager that auto-commits or rolls back."""
        async with self._session_factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------

    async def create_user(self, **kwargs) -> User:
        async with self._session() as sess:
            user = User(**kwargs)
            sess.add(user)
            await sess.flush()
            await sess.refresh(user)
            return user

    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        async with self._session() as sess:
            result = await sess.execute(select(User).where(User.id == user_id))
            return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        async with self._session() as sess:
            result = await sess.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        async with self._session() as sess:
            result = await sess.execute(select(User).where(User.username == username))
            return result.scalar_one_or_none()

    async def list_users(self, active_only: bool = True) -> List[User]:
        async with self._session() as sess:
            stmt = select(User)
            if active_only:
                stmt = stmt.where(User.is_active.is_(True))
            result = await sess.execute(stmt)
            return list(result.scalars().all())

    async def update_user(self, user_id: uuid.UUID, **kwargs) -> Optional[User]:
        async with self._session() as sess:
            await sess.execute(update(User).where(User.id == user_id).values(**kwargs))
            result = await sess.execute(select(User).where(User.id == user_id))
            return result.scalar_one_or_none()

    async def delete_user(self, user_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(User).where(User.id == user_id))

    # ------------------------------------------------------------------
    # Skill
    # ------------------------------------------------------------------

    async def create_skill(self, **kwargs) -> Skill:
        async with self._session() as sess:
            skill = Skill(**kwargs)
            sess.add(skill)
            await sess.flush()
            await sess.refresh(skill)
            return skill

    async def get_skill_by_id(self, skill_id: uuid.UUID) -> Optional[Skill]:
        async with self._session() as sess:
            result = await sess.execute(select(Skill).where(Skill.id == skill_id))
            return result.scalar_one_or_none()

    async def list_skills(self) -> List[Skill]:
        async with self._session() as sess:
            result = await sess.execute(select(Skill))
            return list(result.scalars().all())

    async def delete_skill(self, skill_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Skill).where(Skill.id == skill_id))

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    async def create_session(self, **kwargs) -> Session:
        async with self._session() as sess:
            session = Session(**kwargs)
            sess.add(session)
            await sess.flush()
            await sess.refresh(session)
            return session

    async def get_session_by_id(self, session_id: uuid.UUID) -> Optional[Session]:
        async with self._session() as sess:
            result = await sess.execute(select(Session).where(Session.id == session_id))
            return result.scalar_one_or_none()

    async def get_sessions_by_user(self, user_id: uuid.UUID) -> List[Session]:
        async with self._session() as sess:
            result = await sess.execute(select(Session).where(Session.user_id == user_id))
            return list(result.scalars().all())

    async def update_session(self, session_id: uuid.UUID, **kwargs) -> Optional[Session]:
        async with self._session() as sess:
            await sess.execute(
                update(Session).where(Session.id == session_id).values(**kwargs)
            )
            result = await sess.execute(select(Session).where(Session.id == session_id))
            return result.scalar_one_or_none()

    async def delete_session(self, session_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Session).where(Session.id == session_id))

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    async def create_workflow(self, **kwargs) -> Workflow:
        async with self._session() as sess:
            workflow = Workflow(**kwargs)
            sess.add(workflow)
            await sess.flush()
            await sess.refresh(workflow)
            return workflow

    async def get_workflow_by_id(self, workflow_id: uuid.UUID) -> Optional[Workflow]:
        async with self._session() as sess:
            result = await sess.execute(select(Workflow).where(Workflow.id == workflow_id))
            return result.scalar_one_or_none()

    async def get_workflow_by_name(self, name: str) -> Optional[Workflow]:
        async with self._session() as sess:
            result = await sess.execute(select(Workflow).where(Workflow.name == name))
            return result.scalar_one_or_none()

    async def list_workflows(self) -> List[Workflow]:
        async with self._session() as sess:
            result = await sess.execute(select(Workflow))
            return list(result.scalars().all())

    async def update_workflow(self, workflow_id: uuid.UUID, **kwargs) -> Optional[Workflow]:
        async with self._session() as sess:
            await sess.execute(
                update(Workflow).where(Workflow.id == workflow_id).values(**kwargs)
            )
            result = await sess.execute(select(Workflow).where(Workflow.id == workflow_id))
            return result.scalar_one_or_none()

    async def delete_workflow(self, workflow_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Workflow).where(Workflow.id == workflow_id))

    # ------------------------------------------------------------------
    # Repository
    # ------------------------------------------------------------------

    async def create_repository(self, **kwargs) -> Repository:
        async with self._session() as sess:
            repo = Repository(**kwargs)
            sess.add(repo)
            await sess.flush()
            await sess.refresh(repo)
            return repo

    async def get_repository_by_id(self, repo_id: uuid.UUID) -> Optional[Repository]:
        async with self._session() as sess:
            result = await sess.execute(select(Repository).where(Repository.id == repo_id))
            return result.scalar_one_or_none()

    async def get_repository_by_name(self, repo_name: str) -> Optional[Repository]:
        async with self._session() as sess:
            result = await sess.execute(
                select(Repository).where(Repository.repo_name == repo_name)
            )
            return result.scalar_one_or_none()

    async def list_repositories(self) -> List[Repository]:
        async with self._session() as sess:
            result = await sess.execute(select(Repository))
            return list(result.scalars().all())

    async def update_repository(self, repo_id: uuid.UUID, **kwargs) -> Optional[Repository]:
        async with self._session() as sess:
            await sess.execute(
                update(Repository).where(Repository.id == repo_id).values(**kwargs)
            )
            result = await sess.execute(select(Repository).where(Repository.id == repo_id))
            return result.scalar_one_or_none()

    async def delete_repository(self, repo_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Repository).where(Repository.id == repo_id))

    # ------------------------------------------------------------------
    # RepositoryWorkflowState
    # ------------------------------------------------------------------

    async def create_workflow_state(self, **kwargs) -> RepositoryWorkflowState:
        async with self._session() as sess:
            state = RepositoryWorkflowState(**kwargs)
            sess.add(state)
            await sess.flush()
            await sess.refresh(state)
            return state

    async def get_workflow_state_by_id(
        self, state_id: uuid.UUID
    ) -> Optional[RepositoryWorkflowState]:
        async with self._session() as sess:
            result = await sess.execute(
                select(RepositoryWorkflowState).where(
                    RepositoryWorkflowState.id == state_id
                )
            )
            return result.scalar_one_or_none()

    async def get_workflow_state_by_repo(
        self, repo_id: uuid.UUID
    ) -> Optional[RepositoryWorkflowState]:
        async with self._session() as sess:
            result = await sess.execute(
                select(RepositoryWorkflowState).where(
                    RepositoryWorkflowState.repo_id == repo_id
                )
            )
            return result.scalar_one_or_none()

    async def update_workflow_state(
        self, state_id: uuid.UUID, **kwargs
    ) -> Optional[RepositoryWorkflowState]:
        async with self._session() as sess:
            await sess.execute(
                update(RepositoryWorkflowState)
                .where(RepositoryWorkflowState.id == state_id)
                .values(**kwargs)
            )
            result = await sess.execute(
                select(RepositoryWorkflowState).where(
                    RepositoryWorkflowState.id == state_id
                )
            )
            return result.scalar_one_or_none()

    async def delete_workflow_state(self, state_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(
                delete(RepositoryWorkflowState).where(
                    RepositoryWorkflowState.id == state_id
                )
            )
