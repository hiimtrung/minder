"""
Store Interfaces — backward-compatibility re-export.

CANONICAL LOCATION: ``minder.domain.interfaces.repositories``

This module re-exports all domain repository interfaces so that existing
code with ``from minder.store.interfaces import IOperationalStore`` continues
to work without changes. New code should import from
``minder.domain.interfaces`` directly.
"""

from minder.domain.interfaces.repositories import (  # noqa: F401
    IAdminJobRepository as IAdminJobRepository,
    IAgentRepository as IAgentRepository,
    ICheckpointRepository as ICheckpointRepository,
    IClientRepository as IClientRepository,
    IDocumentRepository as IDocumentRepository,
    IErrorRepository as IErrorRepository,
    IFeedbackRepository as IFeedbackRepository,
    IGraphRepository as IGraphRepository,
    IHistoryRepository as IHistoryRepository,
    IOperationalStore as IOperationalStore,
    IPromptRepository as IPromptRepository,
    IRepositoryRepo as IRepositoryRepo,
    IRuleRepository as IRuleRepository,
    ISessionRepository as ISessionRepository,
    ISkillRepository as ISkillRepository,
    IUserRepository as IUserRepository,
    IVectorStore as IVectorStore,
    IWorkflowRepository as IWorkflowRepository,
    IWorkflowStateRepository as IWorkflowStateRepository,
)
from minder.domain.interfaces.cache import (  # noqa: F401
    ICacheProvider as ICacheProvider,
)
