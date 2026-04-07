"""
Store package — data access layer.

Exports both concrete implementations and domain interfaces.
Application code should depend on interfaces from `minder.store.interfaces`.
"""

from .document import DocumentStore
from .error import ErrorStore
from .feedback import FeedbackStore
from .graph import KnowledgeGraphStore
from .history import HistoryStore
from .interfaces import (
    ICacheProvider,
    IDocumentRepository,
    IErrorRepository,
    IFeedbackRepository,
    IGraphRepository,
    IHistoryRepository,
    IOperationalStore,
    IRepositoryRepo,
    IRuleRepository,
    ISessionRepository,
    ISkillRepository,
    IUserRepository,
    IVectorStore,
    IWorkflowRepository,
    IWorkflowStateRepository,
)
from .relational import RelationalStore
from .repo_state import RepoStateStore
from .rule import RuleStore
from .vector import VectorStore

__all__ = [
    # Domain interfaces
    "ICacheProvider",
    "IDocumentRepository",
    "IErrorRepository",
    "IFeedbackRepository",
    "IGraphRepository",
    "IHistoryRepository",
    "IOperationalStore",
    "IRepositoryRepo",
    "IRuleRepository",
    "ISessionRepository",
    "ISkillRepository",
    "IUserRepository",
    "IVectorStore",
    "IWorkflowRepository",
    "IWorkflowStateRepository",
    # Concrete implementations
    "DocumentStore",
    "ErrorStore",
    "FeedbackStore",
    "HistoryStore",
    "KnowledgeGraphStore",
    "RelationalStore",
    "RepoStateStore",
    "RuleStore",
    "VectorStore",
]
