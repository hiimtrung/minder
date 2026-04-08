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
from typing import Any, AsyncGenerator, List, Optional, cast

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from minder.models import (
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
    User,
    Workflow,
)

_REGISTERED_MODELS = (
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

    async def has_admin_users(self) -> bool:
        async with self._session() as sess:
            result = await sess.execute(select(select(User).where(User.role == "admin").exists()))
            return result.scalar_one_or_none() or False

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
    # Client Gateway
    # ------------------------------------------------------------------

    async def create_client(self, **kwargs) -> Client:
        async with self._session() as sess:
            client = Client(**kwargs)
            sess.add(client)
            await sess.flush()
            await sess.refresh(client)
            return client

    async def get_client_by_id(self, client_id: uuid.UUID) -> Optional[Client]:
        async with self._session() as sess:
            result = await sess.execute(select(Client).where(Client.id == client_id))
            return result.scalar_one_or_none()

    async def get_client_by_slug(self, slug: str) -> Optional[Client]:
        async with self._session() as sess:
            result = await sess.execute(select(Client).where(Client.slug == slug))
            return result.scalar_one_or_none()

    async def list_clients(self) -> List[Client]:
        async with self._session() as sess:
            result = await sess.execute(select(Client))
            return list(result.scalars().all())

    async def update_client(self, client_id: uuid.UUID, **kwargs) -> Optional[Client]:
        async with self._session() as sess:
            await sess.execute(update(Client).where(Client.id == client_id).values(**kwargs))
            result = await sess.execute(select(Client).where(Client.id == client_id))
            return result.scalar_one_or_none()

    async def create_client_api_key(self, **kwargs) -> ClientApiKey:
        async with self._session() as sess:
            key = ClientApiKey(**kwargs)
            sess.add(key)
            await sess.flush()
            await sess.refresh(key)
            return key

    async def list_client_api_keys(self, client_id: uuid.UUID) -> List[ClientApiKey]:
        async with self._session() as sess:
            result = await sess.execute(
                select(ClientApiKey).where(ClientApiKey.client_id == client_id)
            )
            return list(result.scalars().all())

    async def update_client_api_key(self, key_id: uuid.UUID, **kwargs) -> Optional[ClientApiKey]:
        async with self._session() as sess:
            await sess.execute(
                update(ClientApiKey).where(ClientApiKey.id == key_id).values(**kwargs)
            )
            result = await sess.execute(
                select(ClientApiKey).where(ClientApiKey.id == key_id)
            )
            return result.scalar_one_or_none()

    async def create_client_session(self, **kwargs) -> ClientSession:
        async with self._session() as sess:
            client_session = ClientSession(**kwargs)
            sess.add(client_session)
            await sess.flush()
            await sess.refresh(client_session)
            return client_session

    async def get_client_session_by_token_id(self, token_id: str) -> Optional[ClientSession]:
        async with self._session() as sess:
            result = await sess.execute(
                select(ClientSession).where(ClientSession.access_token_id == token_id)
            )
            return result.scalar_one_or_none()

    async def update_client_session(self, session_id: uuid.UUID, **kwargs) -> Optional[ClientSession]:
        async with self._session() as sess:
            await sess.execute(
                update(ClientSession).where(ClientSession.id == session_id).values(**kwargs)
            )
            result = await sess.execute(
                select(ClientSession).where(ClientSession.id == session_id)
            )
            return result.scalar_one_or_none()

    async def create_audit_log(self, **kwargs) -> AuditLog:
        async with self._session() as sess:
            audit_log = AuditLog(**kwargs)
            sess.add(audit_log)
            await sess.flush()
            await sess.refresh(audit_log)
            return audit_log

    async def list_audit_logs(self, *, actor_id: str | None = None) -> List[AuditLog]:
        async with self._session() as sess:
            stmt = select(AuditLog)
            if actor_id is not None:
                stmt = stmt.where(AuditLog.actor_id == actor_id)
            result = await sess.execute(stmt)
            return list(result.scalars().all())

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
    ) -> Document:
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
            return document

    async def get_document_by_path(
        self, source_path: str, *, project: str | None = None
    ) -> Document | None:
        async with self._session() as sess:
            stmt = select(Document).where(Document.source_path == source_path)
            if project is not None:
                stmt = stmt.where(Document.project == project)
            result = await sess.execute(stmt)
            return result.scalar_one_or_none()

    async def list_documents(self, project: str | None = None) -> list[Document]:
        async with self._session() as sess:
            stmt = select(Document)
            if project is not None:
                stmt = stmt.where(Document.project == project)
            result = await sess.execute(stmt)
            return list(result.scalars().all())

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
    ) -> Document:
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
            result = await sess.execute(select(Document).where(Document.id == existing.id))
            return result.scalar_one()

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
    ) -> History:
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
            return history

    async def list_history_for_session(self, session_id: uuid.UUID) -> list[History]:
        async with self._session() as sess:
            result = await sess.execute(
                select(History).where(History.session_id == session_id)
            )
            return list(result.scalars().all())

    async def list_history_for_user(self, user_id: uuid.UUID) -> list[History]:
        async with self._session() as sess:
            result = await sess.execute(
                select(History)
                .join(Session, Session.id == History.session_id)
                .where(Session.user_id == user_id)
            )
            return list(result.scalars().all())

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
    ) -> Error:
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
            return error

    async def list_errors(self) -> list[Error]:
        async with self._session() as sess:
            result = await sess.execute(select(Error))
            return list(result.scalars().all())

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

    async def create_rule(self, **kwargs: Any) -> Rule:
        async with self._session() as sess:
            rule = Rule(**kwargs)
            sess.add(rule)
            await sess.flush()
            await sess.refresh(rule)
            return rule

    async def get_rule_by_id(self, rule_id: uuid.UUID) -> Optional[Rule]:
        async with self._session() as sess:
            result = await sess.execute(select(Rule).where(Rule.id == rule_id))
            return result.scalar_one_or_none()

    async def list_rules(self) -> List[Rule]:
        async with self._session() as sess:
            result = await sess.execute(select(Rule))
            return list(result.scalars().all())

    async def list_by_scope(self, scope: str) -> List[Rule]:
        async with self._session() as sess:
            result = await sess.execute(select(Rule).where(Rule.scope == scope))
            return list(result.scalars().all())

    async def list_active(self) -> List[Rule]:
        async with self._session() as sess:
            result = await sess.execute(select(Rule).where(Rule.active.is_(True)))
            return list(result.scalars().all())

    async def update_rule(self, rule_id: uuid.UUID, **kwargs: Any) -> Optional[Rule]:
        async with self._session() as sess:
            await sess.execute(update(Rule).where(Rule.id == rule_id).values(**kwargs))
            result = await sess.execute(select(Rule).where(Rule.id == rule_id))
            return result.scalar_one_or_none()

    async def delete_rule(self, rule_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Rule).where(Rule.id == rule_id))

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    async def create_feedback(self, **kwargs: Any) -> Feedback:
        async with self._session() as sess:
            fb = Feedback(**kwargs)
            sess.add(fb)
            await sess.flush()
            await sess.refresh(fb)
            return fb

    async def get_feedback_by_id(self, feedback_id: uuid.UUID) -> Optional[Feedback]:
        async with self._session() as sess:
            result = await sess.execute(
                select(Feedback).where(Feedback.id == feedback_id)
            )
            return result.scalar_one_or_none()

    async def list_feedback(self) -> List[Feedback]:
        async with self._session() as sess:
            result = await sess.execute(select(Feedback))
            return list(result.scalars().all())

    async def list_by_entity(
        self, entity_type: str, entity_id: uuid.UUID
    ) -> List[Feedback]:
        async with self._session() as sess:
            result = await sess.execute(
                select(Feedback).where(
                    Feedback.entity_type == entity_type,
                    Feedback.entity_id == entity_id,
                )
            )
            return list(result.scalars().all())

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
    ) -> Optional[Feedback]:
        async with self._session() as sess:
            await sess.execute(
                update(Feedback).where(Feedback.id == feedback_id).values(**kwargs)
            )
            result = await sess.execute(
                select(Feedback).where(Feedback.id == feedback_id)
            )
            return result.scalar_one_or_none()

    async def delete_feedback(self, feedback_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Feedback).where(Feedback.id == feedback_id))
