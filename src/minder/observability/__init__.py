"""Observability package for Minder.

Public re-exports used throughout the application:

    from minder.observability import (
        configure_logging,
        configure_tracing,
        get_tracer,
        trace_async,
        record_tool_call,
        record_auth_event,
        record_http_request,
        AuditEmitter,
        metrics_endpoint,
        CorrelationIdMiddleware,
        AccessLogMiddleware,
    )
"""
from __future__ import annotations

from minder.observability.audit import AuditEmitter
from minder.observability.logging import (
    AccessLogMiddleware,
    CorrelationIdMiddleware,
    JsonFormatter,
    configure_json_logging,
    get_correlation_id,
)
from minder.observability.metrics import (
    metrics_endpoint,
    record_admin_operation,
    record_auth_event,
    record_http_request,
    record_tool_call,
)
from minder.observability.tracing import configure_tracing, get_tracer, trace_async

__all__ = [
    # audit
    "AuditEmitter",
    # logging
    "AccessLogMiddleware",
    "CorrelationIdMiddleware",
    "JsonFormatter",
    "configure_json_logging",
    "get_correlation_id",
    # metrics
    "metrics_endpoint",
    "record_admin_operation",
    "record_auth_event",
    "record_http_request",
    "record_tool_call",
    # tracing
    "configure_tracing",
    "get_tracer",
    "trace_async",
]
