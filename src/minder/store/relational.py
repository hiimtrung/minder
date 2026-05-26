"""
Relational Store — async SQLAlchemy CRUD for all domain entities.

Supports SQLite (dev, via aiosqlite) and PostgreSQL (prod, via asyncpg).
URL examples:
  SQLite  : sqlite+aiosqlite:///path/to/minder.db
  In-mem  : sqlite+aiosqlite:///:memory:
  Postgres: postgresql+asyncpg://user:pass@host/db
"""

import math
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncGenerator, List, Optional, cast

from sqlalchemy import delete, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from minder.models import (
    AdminJob,
    AuditLog,
    Base,
    Client,
    ClientApiKey,
    ClientSession,
    Document,
    Error,
    Feedback,
    History,
    Repository,
    RepositoryWorkflowState,
    Rule,
    Session,
    Skill,
    Prompt,
    SubAgent,
    User,
    Workflow,
    Checkpoint,
)

from minder.domain.entities import (
    PromptSchema,
    UserSchema,
    SkillSchema,
    AdminJobSchema,
    SessionSchema,
    WorkflowSchema,
    RepositorySchema,
    ClientSchema,
    ClientApiKeySchema,
    ClientSessionSchema,
    AuditLogSchema,
    RepositoryWorkflowStateSchema,
    DocumentSchema,
    HistorySchema,
    ErrorSchema,
    RuleSchema,
    FeedbackSchema,
    SubAgentSchema,
)

_REGISTERED_MODELS = (
    AdminJob,
    AuditLog,
    Client,
    ClientApiKey,
    ClientSession,
    Document,
    Error,
    Feedback,
    History,
    Repository,
    RepositoryWorkflowState,
    Rule,
    Session,
    Skill,
    Prompt,
    SubAgent,
    User,
    Workflow,
    Checkpoint,
)


def _filter_agents(
    agents: list[Any],
    *,
    workflow_step: str | None = None,
    tag: str | None = None,
) -> list[Any]:
    if workflow_step:
        agents = [a for a in agents if workflow_step in (a.workflow_steps or [])]
    if tag:
        agents = [a for a in agents if tag in (a.tags or [])]
    return agents


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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
        """Create all tables (idempotent) and apply incremental column migrations."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(self._apply_column_migrations)

    @staticmethod
    def _apply_column_migrations(sync_conn: Any) -> None:
        """Add columns introduced after initial schema creation (safe no-op if column exists)."""
        from sqlalchemy import inspect, text

        inspector = inspect(sync_conn)
        if "users" in inspector.get_table_names():
            existing = {col["name"] for col in inspector.get_columns("users")}
            if "password_hash" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE users ADD COLUMN password_hash VARCHAR DEFAULT NULL")
                )

        if "sessions" in inspector.get_table_names():
            existing = {col["name"] for col in inspector.get_columns("sessions")}
            if "client_id" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE sessions ADD COLUMN client_id VARCHAR(36) DEFAULT NULL")
                )
            if "name" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE sessions ADD COLUMN name VARCHAR DEFAULT NULL")
                )

        if "skills" in inspector.get_table_names():
            existing = {col["name"] for col in inspector.get_columns("skills")}
            if "deprecated" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE skills ADD COLUMN deprecated BOOLEAN NOT NULL DEFAULT 0")
                )
            if "owner_id" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE skills ADD COLUMN owner_id VARCHAR(36) DEFAULT NULL")
                )
            if "scope" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE skills ADD COLUMN scope VARCHAR(10) NOT NULL DEFAULT 'team'")
                )
            if "source_metadata" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE skills ADD COLUMN source_metadata JSON DEFAULT NULL")
                )
            if "excerpt_kind" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE skills ADD COLUMN excerpt_kind VARCHAR NOT NULL DEFAULT 'none'")
                )

        if "workflows" in inspector.get_table_names():
            existing = {col["name"] for col in inspector.get_columns("workflows")}
            if "description" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE workflows ADD COLUMN description VARCHAR NOT NULL DEFAULT ''")
                )
            if "enforcement" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE workflows ADD COLUMN enforcement VARCHAR NOT NULL DEFAULT 'strict'")
                )

        if "repositories" in inspector.get_table_names():
            existing = {col["name"] for col in inspector.get_columns("repositories")}
            if "tracked_branches" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE repositories ADD COLUMN tracked_branches JSON DEFAULT NULL")
                )

        if "repository_workflow_states" in inspector.get_table_names():
            existing = {col["name"] for col in inspector.get_columns("repository_workflow_states")}
            if "branch" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE repository_workflow_states ADD COLUMN branch VARCHAR(255) NOT NULL DEFAULT 'main'")
                )

        if "graph_nodes" in inspector.get_table_names():
            existing = {col["name"] for col in inspector.get_columns("graph_nodes")}
            if "repo_id" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE graph_nodes ADD COLUMN repo_id VARCHAR NOT NULL DEFAULT ''")
                )
            if "branch" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE graph_nodes ADD COLUMN branch VARCHAR NOT NULL DEFAULT ''")
                )

        if "graph_edges" in inspector.get_table_names():
            existing = {col["name"] for col in inspector.get_columns("graph_edges")}
            if "repo_id" not in existing:
                sync_conn.execute(
                    text("ALTER TABLE graph_edges ADD COLUMN repo_id VARCHAR NOT NULL DEFAULT ''")
                )

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
    # Prompts
    # ------------------------------------------------------------------

    async def create_prompt(self, **kwargs: Any) -> PromptSchema:
        async with self._session() as sess:
            item = Prompt(**kwargs)
            sess.add(item)
            await sess.flush()
            await sess.refresh(item)
            return PromptSchema.model_validate(item)

    async def get_prompt_by_id(self, prompt_id: uuid.UUID) -> Optional[PromptSchema]:
        async with self._session() as sess:
            item = await sess.get(Prompt, prompt_id)
            return PromptSchema.model_validate(item) if item else None

    async def get_prompt_by_name(self, name: str) -> Optional[PromptSchema]:
        async with self._session() as sess:
            stmt = select(Prompt).where(Prompt.name == name)
            res = await sess.execute(stmt)
            item = res.scalar_one_or_none()
            return PromptSchema.model_validate(item) if item else None

    async def list_prompts(self) -> List[PromptSchema]:
        async with self._session() as sess:
            stmt = select(Prompt).order_by(Prompt.name)
            res = await sess.execute(stmt)
            items = list(res.scalars().all())
            return [PromptSchema.model_validate(item) for item in items]

    async def update_prompt(
        self, prompt_id: uuid.UUID, **kwargs: Any
    ) -> Optional[PromptSchema]:
        async with self._session() as sess:
            item = await sess.get(Prompt, prompt_id)
            if not item:
                return None
            for k, v in kwargs.items():
                setattr(item, k, v)
            await sess.flush()
            await sess.refresh(item)
            return PromptSchema.model_validate(item)

    async def delete_prompt(self, prompt_id: uuid.UUID) -> None:
        async with self._session() as sess:
            stmt = delete(Prompt).where(Prompt.id == prompt_id)
            await sess.execute(stmt)

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------

    async def create_user(self, **kwargs) -> UserSchema:
        async with self._session() as sess:
            user = User(**kwargs)
            sess.add(user)
            await sess.flush()
            await sess.refresh(user)
            return UserSchema.model_validate(user)

    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[UserSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(User).where(User.id == user_id))
            item = result.scalar_one_or_none()
            return UserSchema.model_validate(item) if item else None

    async def get_user_by_email(self, email: str) -> Optional[UserSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(User).where(User.email == email))
            item = result.scalar_one_or_none()
            return UserSchema.model_validate(item) if item else None

    async def get_user_by_username(self, username: str) -> Optional[UserSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(User).where(User.username == username))
            item = result.scalar_one_or_none()
            return UserSchema.model_validate(item) if item else None

    async def list_users(self, active_only: bool = True) -> List[UserSchema]:
        async with self._session() as sess:
            stmt = select(User)
            if active_only:
                stmt = stmt.where(User.is_active.is_(True))
            result = await sess.execute(stmt)
            items = list(result.scalars().all())
            return [UserSchema.model_validate(item) for item in items]

    async def update_user(self, user_id: uuid.UUID, **kwargs) -> Optional[UserSchema]:
        async with self._session() as sess:
            await sess.execute(update(User).where(User.id == user_id).values(**kwargs))
            result = await sess.execute(select(User).where(User.id == user_id))
            item = result.scalar_one_or_none()
            return UserSchema.model_validate(item) if item else None

    async def delete_user(self, user_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(User).where(User.id == user_id))

    async def has_admin_users(self) -> bool:
        async with self._session() as sess:
            result = await sess.execute(
                select(select(User).where(User.role == "admin").exists())
            )
            return result.scalar_one_or_none() or False

    # ------------------------------------------------------------------
    # Skill
    # ------------------------------------------------------------------

    async def create_skill(self, **kwargs) -> SkillSchema:
        async with self._session() as sess:
            skill = Skill(**kwargs)
            sess.add(skill)
            await sess.flush()
            await sess.refresh(skill)
            return SkillSchema.model_validate(skill)

    async def get_skill_by_id(self, skill_id: uuid.UUID) -> Optional[SkillSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Skill).where(Skill.id == skill_id))
            item = result.scalar_one_or_none()
            return SkillSchema.model_validate(item) if item else None

    async def list_skills(self) -> List[SkillSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Skill))
            items = list(result.scalars().all())
            return [SkillSchema.model_validate(item) for item in items]

    async def list_skills_by_kind(
        self,
        *,
        is_memory: bool,
        exclude_deprecated: bool = True,
        owner_id: uuid.UUID | None = None,
    ) -> List[SkillSchema]:
        _memory_langs = ["markdown", "text", "en", "vi", ""]
        _is_memory_cond = Skill.source_metadata.is_(None) & (
            or_(Skill.language.in_(_memory_langs), Skill.language.is_(None))
        )
        async with self._session() as sess:
            if is_memory:
                stmt = select(Skill).where(_is_memory_cond)
            else:
                stmt = select(Skill).where(~_is_memory_cond)
                if exclude_deprecated:
                    stmt = stmt.where(Skill.deprecated.isnot(True))
            
            if owner_id is not None:
                # Can see their own private memories + team scope memories + legacy memories
                stmt = stmt.where(
                    or_(
                        Skill.owner_id == owner_id,
                        Skill.scope == "team",
                        Skill.owner_id.is_(None)
                    )
                )
            result = await sess.execute(stmt)
            items = list(result.scalars().all())
            return [SkillSchema.model_validate(item) for item in items]

    async def update_skill(self, skill_id: uuid.UUID, **kwargs) -> Optional[SkillSchema]:
        async with self._session() as sess:
            skill = await sess.get(Skill, skill_id)
            if skill is None:
                return None
            for key, value in kwargs.items():
                setattr(skill, key, value)
            await sess.flush()
            await sess.refresh(skill)
            return SkillSchema.model_validate(skill)

    async def delete_skill(self, skill_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Skill).where(Skill.id == skill_id))

    # ------------------------------------------------------------------
    # Admin Jobs
    # ------------------------------------------------------------------

    async def create_admin_job(self, **kwargs: Any) -> AdminJobSchema:
        async with self._session() as sess:
            job = AdminJob(**kwargs)
            sess.add(job)
            await sess.flush()
            await sess.refresh(job)
            return AdminJobSchema.model_validate(job)

    async def get_admin_job_by_id(self, job_id: uuid.UUID) -> Optional[AdminJobSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(AdminJob).where(AdminJob.id == job_id))
            item = result.scalar_one_or_none()
            return AdminJobSchema.model_validate(item) if item else None

    async def list_admin_jobs(
        self,
        *,
        job_type: str | None = None,
        status: str | None = None,
        requested_by_user_id: uuid.UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> List[AdminJobSchema]:
        async with self._session() as sess:
            stmt = select(AdminJob).order_by(AdminJob.created_at.desc())
            if job_type:
                stmt = stmt.where(AdminJob.job_type == job_type)
            if status:
                stmt = stmt.where(AdminJob.status == status)
            if requested_by_user_id is not None:
                stmt = stmt.where(AdminJob.requested_by_user_id == requested_by_user_id)
            if offset:
                stmt = stmt.offset(offset)
            if limit is not None:
                stmt = stmt.limit(limit)
            result = await sess.execute(stmt)
            items = list(result.scalars().all())
            return [AdminJobSchema.model_validate(item) for item in items]

    async def update_admin_job(
        self, job_id: uuid.UUID, **kwargs: Any
    ) -> Optional[AdminJobSchema]:
        async with self._session() as sess:
            job = await sess.get(AdminJob, job_id)
            if job is None:
                return None
            for key, value in kwargs.items():
                setattr(job, key, value)
            await sess.flush()
            await sess.refresh(job)
            return AdminJobSchema.model_validate(job)

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    async def create_session(self, **kwargs) -> SessionSchema:
        async with self._session() as sess:
            session = Session(**kwargs)
            sess.add(session)
            await sess.flush()
            await sess.refresh(session)
            return SessionSchema.model_validate(session)

    async def get_session_by_id(self, session_id: uuid.UUID) -> Optional[SessionSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Session).where(Session.id == session_id))
            item = result.scalar_one_or_none()
            return SessionSchema.model_validate(item) if item else None

    async def get_sessions_by_user(self, user_id: uuid.UUID) -> List[SessionSchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(Session).where(Session.user_id == user_id)
            )
            items = list(result.scalars().all())
            return [SessionSchema.model_validate(item) for item in items]

    async def list_sessions(self) -> List[SessionSchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(Session).order_by(Session.last_active.desc())
            )
            items = list(result.scalars().all())
            return [SessionSchema.model_validate(item) for item in items]

    async def get_sessions_by_client(self, client_id: uuid.UUID) -> List[SessionSchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(Session).where(Session.client_id == client_id)
            )
            items = list(result.scalars().all())
            return [SessionSchema.model_validate(item) for item in items]

    async def find_session_by_name(
        self,
        name: str,
        *,
        user_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
    ) -> Optional[SessionSchema]:
        async with self._session() as sess:
            query = select(Session).where(Session.name == name)
            if client_id is not None:
                query = query.where(Session.client_id == client_id)
            elif user_id is not None:
                query = query.where(Session.user_id == user_id)
            query = query.order_by(Session.last_active.desc()).limit(1)
            result = await sess.execute(query)
            item = result.scalar_one_or_none()
            return SessionSchema.model_validate(item) if item else None

    async def update_session(
        self, session_id: uuid.UUID, **kwargs
    ) -> Optional[SessionSchema]:
        async with self._session() as sess:
            await sess.execute(
                update(Session).where(Session.id == session_id).values(**kwargs)
            )
            result = await sess.execute(select(Session).where(Session.id == session_id))
            item = result.scalar_one_or_none()
            return SessionSchema.model_validate(item) if item else None

    async def delete_session(self, session_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Session).where(Session.id == session_id))

    async def cleanup_expired_sessions(
        self,
        *,
        now: datetime | None = None,
        user_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        reference_time = _normalize_datetime(now) or datetime.now(UTC)
        async with self._session() as sess:
            query = select(Session)
            if user_id is not None:
                query = query.where(Session.user_id == user_id)
            if client_id is not None:
                query = query.where(Session.client_id == client_id)

            result = await sess.execute(query)
            sessions = list(result.scalars().all())
            expired_session_ids = [
                session.id
                for session in sessions
                if session.ttl > 0
                and (
                    (
                        _normalize_datetime(session.last_active)
                        or _normalize_datetime(session.created_at)
                        or reference_time
                    )
                    + timedelta(seconds=session.ttl)
                )
                <= reference_time
            ]
            if not expired_session_ids:
                return {"deleted_sessions": 0, "deleted_history": 0}

            history_result = await sess.execute(
                delete(History).where(History.session_id.in_(expired_session_ids))
            )
            session_result = await sess.execute(
                delete(Session).where(Session.id.in_(expired_session_ids))
            )
            history_cursor = cast(CursorResult[Any], history_result)
            session_cursor = cast(CursorResult[Any], session_result)
            return {
                "deleted_sessions": int(session_cursor.rowcount or 0),
                "deleted_history": int(history_cursor.rowcount or 0),
            }

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    async def create_workflow(self, **kwargs) -> WorkflowSchema:
        async with self._session() as sess:
            workflow = Workflow(**kwargs)
            sess.add(workflow)
            await sess.flush()
            await sess.refresh(workflow)
            return WorkflowSchema.model_validate(workflow)

    async def get_workflow_by_id(self, workflow_id: uuid.UUID) -> Optional[WorkflowSchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(Workflow).where(Workflow.id == workflow_id)
            )
            item = result.scalar_one_or_none()
            return WorkflowSchema.model_validate(item) if item else None

    async def get_workflow_by_name(self, name: str) -> Optional[WorkflowSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Workflow).where(Workflow.name == name))
            item = result.scalar_one_or_none()
            return WorkflowSchema.model_validate(item) if item else None

    async def list_workflows(self) -> List[WorkflowSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Workflow))
            items = list(result.scalars().all())
            return [WorkflowSchema.model_validate(item) for item in items]

    async def update_workflow(
        self, workflow_id: uuid.UUID, **kwargs
    ) -> Optional[WorkflowSchema]:
        async with self._session() as sess:
            await sess.execute(
                update(Workflow).where(Workflow.id == workflow_id).values(**kwargs)
            )
            result = await sess.execute(
                select(Workflow).where(Workflow.id == workflow_id)
            )
            item = result.scalar_one_or_none()
            return WorkflowSchema.model_validate(item) if item else None

    async def delete_workflow(self, workflow_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Workflow).where(Workflow.id == workflow_id))

    # ------------------------------------------------------------------
    # Repository
    # ------------------------------------------------------------------

    async def create_repository(self, **kwargs) -> RepositorySchema:
        async with self._session() as sess:
            repo = Repository(**kwargs)
            sess.add(repo)
            await sess.flush()
            await sess.refresh(repo)
            return RepositorySchema.model_validate(repo)

    async def get_repository_by_id(self, repo_id: uuid.UUID) -> Optional[RepositorySchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(Repository).where(Repository.id == repo_id)
            )
            item = result.scalar_one_or_none()
            return RepositorySchema.model_validate(item) if item else None

    async def get_repository_by_name(self, repo_name: str) -> Optional[RepositorySchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(Repository).where(Repository.repo_name == repo_name)
            )
            item = result.scalar_one_or_none()
            return RepositorySchema.model_validate(item) if item else None

    async def list_repositories(self) -> List[RepositorySchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Repository))
            items = list(result.scalars().all())
            return [RepositorySchema.model_validate(item) for item in items]

    async def update_repository(
        self, repo_id: uuid.UUID, **kwargs
    ) -> Optional[RepositorySchema]:
        async with self._session() as sess:
            await sess.execute(
                update(Repository).where(Repository.id == repo_id).values(**kwargs)
            )
            result = await sess.execute(
                select(Repository).where(Repository.id == repo_id)
            )
            item = result.scalar_one_or_none()
            return RepositorySchema.model_validate(item) if item else None

    async def delete_repository(self, repo_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Repository).where(Repository.id == repo_id))

    # ------------------------------------------------------------------
    # Client Gateway
    # ------------------------------------------------------------------

    async def create_client(self, **kwargs) -> ClientSchema:
        async with self._session() as sess:
            client = Client(**kwargs)
            sess.add(client)
            await sess.flush()
            await sess.refresh(client)
            return ClientSchema.model_validate(client)

    async def get_client_by_id(self, client_id: uuid.UUID) -> Optional[ClientSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Client).where(Client.id == client_id))
            item = result.scalar_one_or_none()
            return ClientSchema.model_validate(item) if item else None

    async def get_client_by_slug(self, slug: str) -> Optional[ClientSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Client).where(Client.slug == slug))
            item = result.scalar_one_or_none()
            return ClientSchema.model_validate(item) if item else None

    async def list_clients(self) -> List[ClientSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Client))
            items = list(result.scalars().all())
            return [ClientSchema.model_validate(item) for item in items]

    async def update_client(self, client_id: uuid.UUID, **kwargs) -> Optional[ClientSchema]:
        async with self._session() as sess:
            await sess.execute(
                update(Client).where(Client.id == client_id).values(**kwargs)
            )
            result = await sess.execute(select(Client).where(Client.id == client_id))
            item = result.scalar_one_or_none()
            return ClientSchema.model_validate(item) if item else None

    async def create_client_api_key(self, **kwargs) -> ClientApiKeySchema:
        async with self._session() as sess:
            key = ClientApiKey(**kwargs)
            sess.add(key)
            await sess.flush()
            await sess.refresh(key)
            return ClientApiKeySchema.model_validate(key)

    async def list_client_api_keys(self, client_id: uuid.UUID) -> List[ClientApiKeySchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(ClientApiKey).where(ClientApiKey.client_id == client_id)
            )
            items = list(result.scalars().all())
            return [ClientApiKeySchema.model_validate(item) for item in items]

    async def update_client_api_key(
        self, key_id: uuid.UUID, **kwargs
    ) -> Optional[ClientApiKeySchema]:
        async with self._session() as sess:
            await sess.execute(
                update(ClientApiKey).where(ClientApiKey.id == key_id).values(**kwargs)
            )
            result = await sess.execute(
                select(ClientApiKey).where(ClientApiKey.id == key_id)
            )
            item = result.scalar_one_or_none()
            return ClientApiKeySchema.model_validate(item) if item else None

    async def create_client_session(self, **kwargs) -> ClientSessionSchema:
        async with self._session() as sess:
            client_session = ClientSession(**kwargs)
            sess.add(client_session)
            await sess.flush()
            await sess.refresh(client_session)
            return ClientSessionSchema.model_validate(client_session)

    async def count_active_client_sessions(self) -> int:
        from sqlalchemy import func as sqlfunc
        from datetime import datetime

        async with self._session() as sess:
            # Using naive comparison for SQLite compatibility
            now = datetime.utcnow()
            stmt = select(sqlfunc.count(ClientSession.id)).where(
                ClientSession.status == "active",
                ClientSession.expires_at > now,
            )
            result = await sess.execute(stmt)
            return result.scalar_one() or 0

    async def get_client_session_by_token_id(
        self, token_id: str
    ) -> Optional[ClientSessionSchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(ClientSession).where(ClientSession.access_token_id == token_id)
            )
            item = result.scalar_one_or_none()
            return ClientSessionSchema.model_validate(item) if item else None

    async def update_client_session(
        self, session_id: uuid.UUID, **kwargs
    ) -> Optional[ClientSessionSchema]:
        async with self._session() as sess:
            await sess.execute(
                update(ClientSession)
                .where(ClientSession.id == session_id)
                .values(**kwargs)
            )
            result = await sess.execute(
                select(ClientSession).where(ClientSession.id == session_id)
            )
            item = result.scalar_one_or_none()
            return ClientSessionSchema.model_validate(item) if item else None

    async def create_audit_log(self, **kwargs) -> AuditLogSchema:
        async with self._session() as sess:
            audit_log = AuditLog(**kwargs)
            sess.add(audit_log)
            await sess.flush()
            await sess.refresh(audit_log)
            return AuditLogSchema.model_validate(audit_log)

    async def list_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        event_type: str | None = None,
        outcome: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> List[AuditLogSchema]:
        from sqlalchemy import desc

        async with self._session() as sess:
            stmt = select(AuditLog).order_by(desc(AuditLog.created_at))
            if actor_id is not None:
                stmt = stmt.where(AuditLog.actor_id == actor_id)
            if event_type is not None:
                stmt = stmt.where(AuditLog.event_type == event_type)
            if outcome is not None:
                stmt = stmt.where(AuditLog.outcome == outcome)
            stmt = stmt.offset(offset)
            if limit is not None:
                stmt = stmt.limit(limit)
            result = await sess.execute(stmt)
            items = list(result.scalars().all())
            return [AuditLogSchema.model_validate(item) for item in items]

    async def count_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        event_type: str | None = None,
        outcome: str | None = None,
    ) -> int:
        from sqlalchemy import func as sqlfunc

        async with self._session() as sess:
            stmt = select(sqlfunc.count()).select_from(AuditLog)
            if actor_id is not None:
                stmt = stmt.where(AuditLog.actor_id == actor_id)
            if event_type is not None:
                stmt = stmt.where(AuditLog.event_type == event_type)
            if outcome is not None:
                stmt = stmt.where(AuditLog.outcome == outcome)
            result = await sess.execute(stmt)
            return result.scalar_one() or 0

    async def get_audit_summary(
        self,
        *,
        actor_id: str | None = None,
        event_type: str | None = None,
        outcome: str | None = None,
        group_by: str = "event_type",
    ) -> dict[str, int]:
        from sqlalchemy import func as sqlfunc

        async with self._session() as sess:
            # Handle nested group_by like "audit_metadata.client_id"
            if "." in group_by:
                parent, child = group_by.split(".", 1)
                col = getattr(AuditLog, parent)[child].as_string()
            else:
                col = getattr(AuditLog, group_by)

            stmt = select(col, sqlfunc.count()).group_by(col)

            if actor_id is not None:
                stmt = stmt.where(AuditLog.actor_id == actor_id)
            if event_type is not None:
                stmt = stmt.where(AuditLog.event_type == event_type)
            if outcome is not None:
                stmt = stmt.where(AuditLog.outcome == outcome)

            result = await sess.execute(stmt)
            return {
                str(row[0]) if row[0] is not None else "unknown": int(row[1])
                for row in result.all()
            }

    # ------------------------------------------------------------------
    # RepositoryWorkflowState
    # ------------------------------------------------------------------

    async def create_workflow_state(self, **kwargs) -> RepositoryWorkflowStateSchema:
        async with self._session() as sess:
            state = RepositoryWorkflowState(**kwargs)
            sess.add(state)
            await sess.flush()
            await sess.refresh(state)
            return RepositoryWorkflowStateSchema.model_validate(state)

    async def get_workflow_state_by_id(
        self, state_id: uuid.UUID
    ) -> Optional[RepositoryWorkflowStateSchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(RepositoryWorkflowState).where(
                    RepositoryWorkflowState.id == state_id
                )
            )
            item = result.scalar_one_or_none()
            return RepositoryWorkflowStateSchema.model_validate(item) if item else None

    async def get_workflow_state_by_repo(
        self, repo_id: uuid.UUID, *, branch: str = "main"
    ) -> Optional[RepositoryWorkflowStateSchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(RepositoryWorkflowState).where(
                    RepositoryWorkflowState.repo_id == repo_id,
                    RepositoryWorkflowState.branch == branch
                )
            )
            item = result.scalar_one_or_none()
            return RepositoryWorkflowStateSchema.model_validate(item) if item else None

    async def update_workflow_state(
        self, state_id: uuid.UUID, **kwargs
    ) -> Optional[RepositoryWorkflowStateSchema]:
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
            item = result.scalar_one_or_none()
            return RepositoryWorkflowStateSchema.model_validate(item) if item else None

    # ------------------------------------------------------------------
    # Checkpoint
    # ------------------------------------------------------------------

    async def get_checkpoint(self, thread_id: str) -> dict[str, Any] | None:
        from sqlalchemy import select

        async with self._session() as sess:
            # We want the latest checkpoint for the thread if not filtering by checkpoint_id,
            # but usually LangGraph asks for a specific thread_id.
            stmt = select(Checkpoint).where(Checkpoint.thread_id == thread_id).order_by(Checkpoint.created_at.desc()).limit(1)
            result = await sess.execute(stmt)
            chk = result.scalar_one_or_none()
            if not chk:
                return None
            return {
                "checkpoint_id": chk.checkpoint_id,
                "checkpoint": chk.checkpoint,
                "metadata": chk.metadata_,
            }

    async def save_checkpoint(
        self,
        thread_id: str,
        checkpoint_id: str,
        checkpoint: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        async with self._session() as sess:
            chk = Checkpoint(
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                checkpoint=checkpoint,
                metadata_=metadata or {},
            )
            sess.add(chk)
            await sess.flush()

    async def list_checkpoints(
        self, thread_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        from sqlalchemy import select

        async with self._session() as sess:
            stmt = (
                select(Checkpoint)
                .where(Checkpoint.thread_id == thread_id)
                .order_by(Checkpoint.created_at.desc())
                .limit(limit)
            )
            result = await sess.execute(stmt)
            records = result.scalars().all()
            return [
                {
                    "checkpoint_id": r.checkpoint_id,
                    "checkpoint": r.checkpoint,
                    "metadata": r.metadata_,
                }
                for r in records
            ]

    async def delete_workflow_state(self, state_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(
                delete(RepositoryWorkflowState).where(
                    RepositoryWorkflowState.id == state_id
                )
            )

    # ------------------------------------------------------------------
    # Document
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
    ) -> DocumentSchema:
        async with self._session() as sess:
            document = Document(
                id=uuid.uuid4(),
                title=title,
                content=content,
                doc_type=doc_type,
                source_path=source_path,
                chunks=chunks or {},
                embedding=embedding,
                project=project,
            )
            sess.add(document)
            await sess.flush()
            await sess.refresh(document)
            return DocumentSchema.model_validate(document)

    async def get_document_by_path(
        self, source_path: str, *, project: str | None = None
    ) -> DocumentSchema | None:
        async with self._session() as sess:
            stmt = select(Document).where(Document.source_path == source_path)
            if project is not None:
                stmt = stmt.where(Document.project == project)
            result = await sess.execute(stmt)
            item = result.scalar_one_or_none()
            return DocumentSchema.model_validate(item) if item else None

    async def get_documents_by_ids(self, doc_ids: list[uuid.UUID]) -> list[DocumentSchema]:
        if not doc_ids:
            return []
        async with self._session() as sess:
            stmt = select(Document).where(Document.id.in_(doc_ids))
            result = await sess.execute(stmt)
            items = list(result.scalars().all())
            return [DocumentSchema.model_validate(item) for item in items]

    async def list_documents(self, project: str | None = None) -> list[DocumentSchema]:
        async with self._session() as sess:
            stmt = select(Document)
            if project is not None:
                stmt = stmt.where(Document.project == project)
            result = await sess.execute(stmt)
            items = list(result.scalars().all())
            return [DocumentSchema.model_validate(item) for item in items]

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
    ) -> DocumentSchema:
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

        async with self._session() as sess:
            await sess.execute(
                update(Document)
                .where(Document.id == existing.id)
                .values(
                    title=title,
                    content=content,
                    doc_type=doc_type,
                    chunks=chunks or {},
                    embedding=embedding,
                    project=project,
                )
            )
            result = await sess.execute(
                select(Document).where(Document.id == existing.id)
            )
            item = result.scalar_one()
            return DocumentSchema.model_validate(item)

    async def delete_documents_not_in_paths(
        self, *, project: str, keep_paths: set[str]
    ) -> None:
        async with self._session() as sess:
            stmt = delete(Document).where(Document.project == project)
            if keep_paths:
                stmt = stmt.where(Document.source_path.not_in(keep_paths))
            await sess.execute(stmt)

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
    ) -> HistorySchema:
        async with self._session() as sess:
            history = History(
                id=uuid.uuid4(),
                session_id=session_id,
                role=role,
                content=content,
                reasoning_trace=reasoning_trace,
                tool_calls=tool_calls or {},
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )
            sess.add(history)
            await sess.flush()
            await sess.refresh(history)
            return HistorySchema.model_validate(history)

    async def list_history_for_session(self, session_id: uuid.UUID) -> list[HistorySchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(History).where(History.session_id == session_id)
            )
            items = list(result.scalars().all())
            return [HistorySchema.model_validate(item) for item in items]

    async def list_history_for_user(self, user_id: uuid.UUID) -> list[HistorySchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(History)
                .join(Session, Session.id == History.session_id)
                .where(Session.user_id == user_id)
            )
            items = list(result.scalars().all())
            return [HistorySchema.model_validate(item) for item in items]

    async def delete_history_for_session(self, session_id: uuid.UUID) -> int:
        async with self._session() as sess:
            result = await sess.execute(
                delete(History).where(History.session_id == session_id)
            )
            cursor = cast(CursorResult[Any], result)
            return int(cursor.rowcount or 0)

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
    ) -> ErrorSchema:
        async with self._session() as sess:
            error = Error(
                id=uuid.uuid4(),
                error_code=error_code,
                error_message=error_message,
                stack_trace=stack_trace,
                context=context or {},
                resolution=resolution,
                embedding=embedding,
                resolved=resolved,
            )
            sess.add(error)
            await sess.flush()
            await sess.refresh(error)
            return ErrorSchema.model_validate(error)

    async def list_errors(self) -> list[ErrorSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Error))
            items = list(result.scalars().all())
            return [ErrorSchema.model_validate(item) for item in items]

    async def search_errors(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = await self.list_errors()
        query_vector = self._text_vector(query)
        ranked = []
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

    # ------------------------------------------------------------------
    # Rule
    # ------------------------------------------------------------------

    async def create_rule(self, **kwargs: Any) -> RuleSchema:
        async with self._session() as sess:
            rule = Rule(**kwargs)
            sess.add(rule)
            await sess.flush()
            await sess.refresh(rule)
            return RuleSchema.model_validate(rule)

    async def get_rule_by_id(self, rule_id: uuid.UUID) -> Optional[RuleSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Rule).where(Rule.id == rule_id))
            item = result.scalar_one_or_none()
            return RuleSchema.model_validate(item) if item else None

    async def list_rules(self) -> List[RuleSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Rule))
            items = list(result.scalars().all())
            return [RuleSchema.model_validate(item) for item in items]

    async def list_by_scope(self, scope: str) -> List[RuleSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Rule).where(Rule.scope == scope))
            items = list(result.scalars().all())
            return [RuleSchema.model_validate(item) for item in items]

    async def list_active(self) -> List[RuleSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Rule).where(Rule.active.is_(True)))
            items = list(result.scalars().all())
            return [RuleSchema.model_validate(item) for item in items]

    async def update_rule(self, rule_id: uuid.UUID, **kwargs: Any) -> Optional[RuleSchema]:
        async with self._session() as sess:
            await sess.execute(update(Rule).where(Rule.id == rule_id).values(**kwargs))
            result = await sess.execute(select(Rule).where(Rule.id == rule_id))
            item = result.scalar_one_or_none()
            return RuleSchema.model_validate(item) if item else None

    async def delete_rule(self, rule_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Rule).where(Rule.id == rule_id))

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    async def create_feedback(self, **kwargs: Any) -> FeedbackSchema:
        async with self._session() as sess:
            fb = Feedback(**kwargs)
            sess.add(fb)
            await sess.flush()
            await sess.refresh(fb)
            return FeedbackSchema.model_validate(fb)

    async def get_feedback_by_id(self, feedback_id: uuid.UUID) -> Optional[FeedbackSchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(Feedback).where(Feedback.id == feedback_id)
            )
            item = result.scalar_one_or_none()
            return FeedbackSchema.model_validate(item) if item else None

    async def list_feedback(self) -> List[FeedbackSchema]:
        async with self._session() as sess:
            result = await sess.execute(select(Feedback))
            items = list(result.scalars().all())
            return [FeedbackSchema.model_validate(item) for item in items]

    async def list_by_entity(
        self, entity_type: str, entity_id: uuid.UUID
    ) -> List[FeedbackSchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(Feedback).where(
                    Feedback.entity_type == entity_type,
                    Feedback.entity_id == entity_id,
                )
            )
            items = list(result.scalars().all())
            return [FeedbackSchema.model_validate(item) for item in items]

    async def average_rating(self, entity_id: uuid.UUID) -> Optional[float]:
        from sqlalchemy import func as sa_func

        async with self._session() as sess:
            result = await sess.execute(
                select(sa_func.avg(Feedback.rating)).where(
                    Feedback.entity_id == entity_id
                )
            )
            avg = result.scalar_one_or_none()
            return float(avg) if avg is not None else None

    async def update_feedback(
        self, feedback_id: uuid.UUID, **kwargs: Any
    ) -> Optional[FeedbackSchema]:
        async with self._session() as sess:
            await sess.execute(
                update(Feedback).where(Feedback.id == feedback_id).values(**kwargs)
            )
            result = await sess.execute(
                select(Feedback).where(Feedback.id == feedback_id)
            )
            item = result.scalar_one_or_none()
            return FeedbackSchema.model_validate(item) if item else None

    async def delete_feedback(self, feedback_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Feedback).where(Feedback.id == feedback_id))

    # ------------------------------------------------------------------
    # SubAgent Repository
    # ------------------------------------------------------------------

    async def create_agent(self, **kwargs: Any) -> SubAgentSchema:
        async with self._session() as sess:
            agent = SubAgent(**kwargs)
            sess.add(agent)
            await sess.flush()
            await sess.refresh(agent)
            return SubAgentSchema.model_validate(agent)

    async def get_agent_by_id(self, agent_id: uuid.UUID) -> Optional[SubAgentSchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(SubAgent).where(SubAgent.id == agent_id)
            )
            item = result.scalar_one_or_none()
            return SubAgentSchema.model_validate(item) if item else None

    async def get_agent_by_name(self, name: str) -> Optional[SubAgentSchema]:
        async with self._session() as sess:
            result = await sess.execute(
                select(SubAgent).where(SubAgent.name == name)
            )
            item = result.scalar_one_or_none()
            return SubAgentSchema.model_validate(item) if item else None

    async def list_agents(
        self,
        *,
        workflow_step: str | None = None,
        tag: str | None = None,
        is_default: bool | None = None,
    ) -> List[SubAgentSchema]:
        async with self._session() as sess:
            stmt = select(SubAgent)
            if is_default is not None:
                stmt = stmt.where(SubAgent.is_default == is_default)
            result = await sess.execute(stmt)
            orm_agents = list(result.scalars().all())
            agents = [SubAgentSchema.model_validate(a) for a in orm_agents]
        return _filter_agents(agents, workflow_step=workflow_step, tag=tag)

    async def upsert_agent(self, name: str, **kwargs: Any) -> SubAgentSchema:
        existing = await self.get_agent_by_name(name)
        if existing is not None:
            async with self._session() as sess:
                await sess.execute(
                    update(SubAgent).where(SubAgent.name == name).values(**kwargs)
                )
                result = await sess.execute(
                    select(SubAgent).where(SubAgent.name == name)
                )
                item = result.scalar_one()
                return SubAgentSchema.model_validate(item)
        return await self.create_agent(name=name, **kwargs)

    async def update_agent(
        self, agent_id: uuid.UUID, **kwargs: Any
    ) -> Optional[SubAgentSchema]:
        async with self._session() as sess:
            await sess.execute(
                update(SubAgent).where(SubAgent.id == agent_id).values(**kwargs)
            )
            result = await sess.execute(
                select(SubAgent).where(SubAgent.id == agent_id)
            )
            item = result.scalar_one_or_none()
            return SubAgentSchema.model_validate(item) if item else None

    async def delete_agent(self, agent_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(SubAgent).where(SubAgent.id == agent_id))
