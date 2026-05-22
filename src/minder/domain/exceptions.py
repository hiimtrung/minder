"""
Domain Exceptions — business-rule violations and domain errors.

These exceptions are defined in the domain layer so that application and
infrastructure code can raise domain-meaningful errors without depending
on framework-specific exception classes.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-level exceptions."""

    def __init__(self, message: str, *, code: str = "DOMAIN_ERROR") -> None:
        super().__init__(message)
        self.code = code


class AuthError(DomainError):
    """Authentication or authorization failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message, code=code)
        self.message = message  # backward compat with auth.service.AuthError

    def __repr__(self) -> str:
        return f"AuthError(code={self.code!r}, message={self.message!r})"


class EntityNotFoundError(DomainError):
    """Requested entity does not exist in the store."""

    def __init__(self, entity_type: str, entity_id: str) -> None:
        super().__init__(
            f"{entity_type} '{entity_id}' not found",
            code="ENTITY_NOT_FOUND",
        )
        self.entity_type = entity_type
        self.entity_id = entity_id


class ValidationError(DomainError):
    """Input validation failure at the domain level."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message, code="VALIDATION_ERROR")
        self.field = field


class WorkflowViolationError(DomainError):
    """Workflow step transition or guard violation."""

    def __init__(
        self,
        message: str,
        *,
        current_step: str | None = None,
        requested_step: str | None = None,
    ) -> None:
        super().__init__(message, code="WORKFLOW_VIOLATION")
        self.current_step = current_step
        self.requested_step = requested_step


class RateLimitError(DomainError):
    """Rate limit exceeded for a principal or tool."""

    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        super().__init__(message, code="RATE_LIMIT_EXCEEDED")
        self.retry_after = retry_after


class InfrastructureError(DomainError):
    """Failure in an infrastructure component (DB, vector store, etc.)."""

    def __init__(self, message: str, *, component: str = "unknown") -> None:
        super().__init__(message, code="INFRASTRUCTURE_ERROR")
        self.component = component
