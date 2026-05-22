"""
Domain Interfaces — Protocol classes for Dependency Inversion.

Infrastructure adapters implement these protocols.
Application use-cases depend only on these interfaces.
"""

from minder.domain.interfaces.cache import ICacheProvider
from minder.domain.interfaces.embedding import IEmbeddingProvider
from minder.domain.interfaces.llm import ILLMProvider
from minder.domain.interfaces.repositories import (
    IAdminJobRepository,
    IAgentRepository,
    ICheckpointRepository,
    IClientRepository,
    IDocumentRepository,
    IErrorRepository,
    IFeedbackRepository,
    IGraphRepository,
    IHistoryRepository,
    IOperationalStore,
    IPromptRepository,
    IRepositoryRepo,
    IRuleRepository,
    ISessionRepository,
    ISkillRepository,
    IUserRepository,
    IVectorStore,
    IWorkflowRepository,
    IWorkflowStateRepository,
)

__all__ = [
    "IAdminJobRepository",
    "IAgentRepository",
    "ICacheProvider",
    "ICheckpointRepository",
    "IClientRepository",
    "IDocumentRepository",
    "IEmbeddingProvider",
    "IErrorRepository",
    "IFeedbackRepository",
    "IGraphRepository",
    "IHistoryRepository",
    "ILLMProvider",
    "IOperationalStore",
    "IPromptRepository",
    "IRepositoryRepo",
    "IRuleRepository",
    "ISessionRepository",
    "ISkillRepository",
    "IUserRepository",
    "IVectorStore",
    "IWorkflowRepository",
    "IWorkflowStateRepository",
]
