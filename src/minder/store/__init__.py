"""
Store package — data access layer.

Exports both concrete implementations and domain interfaces.
Application code should depend on interfaces from `minder.store.interfaces`.
"""

from .document import DocumentStore
from .error import ErrorStore
from .history import HistoryStore
from .interfaces import (
    ICacheProvider,
    IDocumentRepository,
    IErrorRepository,
    IHistoryRepository,
    IOperationalStore,
    IRepositoryRepo,
    ISessionRepository,
    ISkillRepository,
    IUserRepository,
    IVectorStore,
    IWorkflowRepository,
    IWorkflowStateRepository,
)
from .relational import RelationalStore
from .repo_state import RepoStateStore
from .vector import VectorStore

__all__ = [
    # Domain interfaces
    "ICacheProvider",
    "IDocumentRepository",
    "IErrorRepository",
    "IHistoryRepository",
    "IOperationalStore",
    "IRepositoryRepo",
    "ISessionRepository",
    "ISkillRepository",
    "IUserRepository",
    "IVectorStore",
    "IWorkflowRepository",
    "IWorkflowStateRepository",
    # Concrete implementations
    "DocumentStore",
    "ErrorStore",
    "HistoryStore",
    "RelationalStore",
    "RepoStateStore",
    "VectorStore",
]
