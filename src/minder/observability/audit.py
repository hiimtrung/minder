"""Durable audit event emitter for Minder.

Wraps ``store.create_audit_log()`` with a higher-level convenience API and
also emits a structured log entry for every event so that operators have
both persistent audit records and real-time log streams.

Usage::

    emitter = AuditEmitter(store=store)

    await emitter.emit(
        actor_type="admin",
        actor_id=str(admin.id),
        event_type="client.created",
        resource_type="client",
        resource_id=str(client.id),
        outcome="success",
    )

    # Convenience helpers
    await emitter.client_created(actor_id=..., client_id=..., metadata={...})
    await emitter.key_rotated(actor_id=..., client_id=...)
    await emitter.auth_login(actor_id=..., outcome="success")
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from minder.store.interfaces import IOperationalStore

_log = logging.getLogger(__name__)


class AuditEmitter:
    """Emit structured audit events to the operational store and to the log.

    An ``AuditEmitter`` is safe to construct once at application start and
    reused across requests.  All methods are coroutines because the store
    write is async.
    """

    def __init__(self, store: IOperationalStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Core emit
    # ------------------------------------------------------------------

    async def emit(
        self,
        *,
        actor_type: str,
        actor_id: str,
        event_type: str,
        resource_type: str,
        resource_id: str,
        outcome: str = "success",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist one audit event and write it to the structured log.

        Args:
            actor_type:    Who performed the action (``"admin"`` | ``"client"`` | ``"system"``).
            actor_id:      UUID string of the actor.
            event_type:    Dot-separated action label (``"client.created"``, ``"key.rotated"``…).
            resource_type: Type of the affected resource (``"client"`` | ``"key"`` | …).
            resource_id:   UUID string of the affected resource.
            outcome:       ``"success"`` | ``"failure"`` | ``"denied"``.
            metadata:      Optional extra structured data persisted with the event.
        """
        audit_metadata = metadata or {}

        try:
            await self._store.create_audit_log(
                id=str(uuid.uuid4()),
                actor_type=actor_type,
                actor_id=actor_id,
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=outcome,
                audit_metadata=audit_metadata,
            )
        except Exception:
            _log.exception(
                "Failed to persist audit event",
                extra={
                    "audit_event_type": event_type,
                    "audit_actor_id": actor_id,
                    "audit_resource_id": resource_id,
                    "audit_outcome": outcome,
                },
            )

        _log.info(
            "audit: %s %s → %s",
            actor_type,
            event_type,
            outcome,
            extra={
                "audit_actor_type": actor_type,
                "audit_actor_id": actor_id,
                "audit_event_type": event_type,
                "audit_resource_type": resource_type,
                "audit_resource_id": resource_id,
                "audit_outcome": outcome,
                **audit_metadata,
            },
        )

    # ------------------------------------------------------------------
    # Convenience helpers — auth/lifecycle events
    # ------------------------------------------------------------------

    async def auth_login(
        self,
        *,
        actor_id: str,
        actor_type: str = "admin",
        outcome: str = "success",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.emit(
            actor_type=actor_type,
            actor_id=actor_id,
            event_type="auth.login",
            resource_type="session",
            resource_id=actor_id,
            outcome=outcome,
            metadata=metadata,
        )

    async def auth_logout(
        self,
        *,
        actor_id: str,
        actor_type: str = "admin",
    ) -> None:
        await self.emit(
            actor_type=actor_type,
            actor_id=actor_id,
            event_type="auth.logout",
            resource_type="session",
            resource_id=actor_id,
        )

    async def client_created(
        self,
        *,
        actor_id: str,
        client_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.emit(
            actor_type="admin",
            actor_id=actor_id,
            event_type="client.created",
            resource_type="client",
            resource_id=client_id,
            metadata=metadata,
        )

    async def client_updated(
        self,
        *,
        actor_id: str,
        client_id: str,
        fields_changed: list[str] | None = None,
    ) -> None:
        await self.emit(
            actor_type="admin",
            actor_id=actor_id,
            event_type="client.updated",
            resource_type="client",
            resource_id=client_id,
            metadata={"fields_changed": fields_changed or []},
        )

    async def key_rotated(
        self,
        *,
        actor_id: str,
        client_id: str,
    ) -> None:
        await self.emit(
            actor_type="admin",
            actor_id=actor_id,
            event_type="key.rotated",
            resource_type="client",
            resource_id=client_id,
        )

    async def key_revoked(
        self,
        *,
        actor_id: str,
        client_id: str,
    ) -> None:
        await self.emit(
            actor_type="admin",
            actor_id=actor_id,
            event_type="key.revoked",
            resource_type="client",
            resource_id=client_id,
        )

    async def token_exchanged(
        self,
        *,
        actor_id: str,
        client_id: str,
        scopes: list[str] | None = None,
        outcome: str = "success",
    ) -> None:
        await self.emit(
            actor_type="client",
            actor_id=actor_id,
            event_type="token.exchanged",
            resource_type="client",
            resource_id=client_id,
            outcome=outcome,
            metadata={"scopes": scopes or []},
        )

    async def tool_call(
        self,
        *,
        actor_id: str,
        tool_name: str,
        outcome: str = "success",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.emit(
            actor_type="client",
            actor_id=actor_id,
            event_type=f"tool.{tool_name}",
            resource_type="tool",
            resource_id=tool_name,
            outcome=outcome,
            metadata=metadata,
        )
