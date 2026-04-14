"""Prometheus metrics registry for Minder.

Registers all application-level counters, histograms, and gauges and
exposes a WSGI/ASGI-compatible handler that can be mounted at `/metrics`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from minder.store.interfaces import IOperationalStore

# ---------------------------------------------------------------------------
# Shared registry
# ---------------------------------------------------------------------------

REGISTRY = CollectorRegistry(auto_describe=True)

# ---------------------------------------------------------------------------
# Tool-call metrics
# ---------------------------------------------------------------------------

TOOL_CALLS_TOTAL = Counter(
    "minder_tool_calls_total",
    "Total number of MCP tool invocations.",
    ["tool_name", "outcome", "client_id"],  # Added client_id
    registry=REGISTRY,
)

TOOL_CALL_DURATION = Histogram(
    "minder_tool_call_duration_seconds",
    "MCP tool call latency in seconds.",
    ["tool_name", "client_id"],  # Added client_id
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Auth / session metrics
# ---------------------------------------------------------------------------

AUTH_EVENTS_TOTAL = Counter(
    "minder_auth_events_total",
    "Total number of authentication and authorisation events.",
    ["event_type", "outcome", "client_id"],  # Added client_id
    registry=REGISTRY,
)

ACTIVE_CLIENT_SESSIONS = Gauge(
    "minder_active_client_sessions",
    "Number of active MCP client sessions tracked in the cache.",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# HTTP metrics
# ---------------------------------------------------------------------------

HTTP_REQUESTS_TOTAL = Counter(
    "minder_http_requests_total",
    "Total HTTP requests handled.",
    ["method", "path_template", "status"],
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION = Histogram(
    "minder_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path_template"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Admin-operation metrics
# ---------------------------------------------------------------------------

ADMIN_OPERATIONS_TOTAL = Counter(
    "minder_admin_operations_total",
    "Total admin API operations.",
    ["operation", "outcome"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def record_tool_call(
    tool_name: str, 
    outcome: str, 
    duration_seconds: float, 
    client_id: str = "unknown"
) -> None:
    """Record a tool invocation outcome and latency."""
    import logging
    logging.getLogger("minder.metrics").debug(
        "Recording tool call: %s outcome=%s client=%s", 
        tool_name, outcome, client_id
    )
    TOOL_CALLS_TOTAL.labels(tool_name=tool_name, outcome=outcome, client_id=client_id).inc()
    TOOL_CALL_DURATION.labels(tool_name=tool_name, client_id=client_id).observe(duration_seconds)


async def record_auth_event(
    event_type: str, 
    outcome: str, 
    client_id: str = "unknown",
    store: IOperationalStore | None = None
) -> None:
    """Record an auth/session lifecycle event."""
    AUTH_EVENTS_TOTAL.labels(event_type=event_type, outcome=outcome, client_id=client_id).inc()
    
    if store is not None:
        try:
            await store.create_audit_log(
                actor_type="auth",
                actor_id=client_id,
                event_type=event_type,
                resource_type="session",
                resource_id=client_id,
                outcome=outcome,
                audit_metadata={"client_id": client_id}
            )
        except Exception:
            pass


def record_http_request(
    method: str,
    path_template: str,
    status: int,
    duration_seconds: float,
) -> None:
    """Record a completed HTTP request."""
    HTTP_REQUESTS_TOTAL.labels(
        method=method, path_template=path_template, status=str(status)
    ).inc()
    HTTP_REQUEST_DURATION.labels(
        method=method, path_template=path_template
    ).observe(duration_seconds)


async def record_admin_operation(
    operation: str, 
    outcome: str, 
    actor_id: str = "unknown", 
    store: IOperationalStore | None = None
) -> None:
    """Record an admin API operation (outcome: 'success' | 'error')."""
    ADMIN_OPERATIONS_TOTAL.labels(operation=operation, outcome=outcome).inc()

    if store is not None:
        try:
            await store.create_audit_log(
                actor_type="admin",
                actor_id=actor_id,
                event_type="admin_op",
                resource_type="admin_api",
                resource_id=operation,
                outcome=outcome,
                audit_metadata={"operation": operation}
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Starlette endpoint
# ---------------------------------------------------------------------------


async def metrics_endpoint(request: "Request") -> "Response":  # noqa: ARG001
    """ASGI route handler that returns Prometheus text format metrics."""
    from starlette.responses import Response as StarletteResponse

    output = generate_latest(REGISTRY)
    return StarletteResponse(
        content=output,
        media_type=CONTENT_TYPE_LATEST,
    )


def get_registry_snapshot() -> dict[str, Any]:
    """Return a lightweight dict snapshot of registered metric names (for tests)."""
    return {
        metric.describe()[0].name: metric.describe()[0].type  # type: ignore[union-attr]
        for metric in REGISTRY._names_to_collectors.values()  # noqa: SLF001
        if hasattr(metric, "describe")
    }


def _counter_total(
    counter: Counter, 
    filter_label: str | None = None, 
    filter_value: str | None = None
) -> float:
    """Sum all label-value combinations of a Counter, optionally filtering."""
    total = 0.0
    label_names = counter._labelnames  # noqa: SLF001
    filter_idx = label_names.index(filter_label) if filter_label in label_names else None

    for label_tuple, child in counter._metrics.items():  # noqa: SLF001
        if filter_idx is not None and filter_value:
            if label_tuple[filter_idx] != filter_value:
                continue
        total += cast(Any, child)._value.get()  # noqa: SLF001
    return total


def _counter_by_label(
    counter: Counter, 
    label_name: str, 
    filter_label: str | None = None, 
    filter_value: str | None = None
) -> dict[str, float]:
    """Aggregate a Counter by a single label, optionally filtering."""
    label_names: tuple[str, ...] = counter._labelnames  # noqa: SLF001
    if label_name not in label_names:
        return {}
    
    idx = label_names.index(label_name)
    filter_idx = label_names.index(filter_label) if filter_label in label_names else None
    
    result: dict[str, float] = {}
    for label_tuple, child in counter._metrics.items():  # noqa: SLF001
        if filter_idx is not None and filter_value:
            if label_tuple[filter_idx] != filter_value:
                continue
        key = label_tuple[idx]
        result[key] = result.get(key, 0.0) + cast(Any, child)._value.get()  # noqa: SLF001
    return result


async def get_metrics_summary(
    store: IOperationalStore,
    active_sessions: int | None = None,
    client_id: str | None = None,
    event_type: str | None = None,
    outcome: str | None = None,
) -> dict[str, Any]:
    """Return a combined summary of persistent audit logs and runtime metrics.

    Prioritises the operational store for persistent events (tool calls, auth, admin ops)
    while falling back to Prometheus for ephemeral runtime stats (active sessions, HTTP).
    """
    import logging
    logger = logging.getLogger("minder.metrics")

    # Metrics from Store (Persistent)
    # 1. Tool Calls
    tool_by_outcome = await store.get_audit_summary(
        actor_id=client_id, 
        event_type="tool_call", 
        outcome=outcome,
        group_by="outcome"
    )
    tool_by_client = await store.get_audit_summary(
        event_type="tool_call",
        outcome=outcome,
        group_by="audit_metadata.client_id" # This depends on Mongo/SQL support for nested fields
    )
    tool_by_name = await store.get_audit_summary(
        actor_id=client_id,
        event_type="tool_call",
        outcome=outcome,
        group_by="tool_name"
    )
    tool_total = sum(tool_by_outcome.values())

    # 2. Auth Events (we combine tool_calls and auth_events for a "unified" view if needed)
    auth_by_type = await store.get_audit_summary(
        actor_id=client_id,
        outcome=outcome,
        group_by="event_type"
    )
    auth_total = sum(auth_by_type.values())

    # 3. Admin Ops
    admin_by_outcome = await store.get_audit_summary(
        event_type="admin_op",
        outcome=outcome,
        group_by="outcome"
    )
    admin_total = sum(admin_by_outcome.values())

    # Runtime stats from Prometheus (Fallback/Ephemeral)
    effective_sessions = active_sessions if active_sessions is not None else ACTIVE_CLIENT_SESSIONS._value.get()
    
    logger.info("Serving persistent metrics summary: sessions=%s, tool_calls=%s", effective_sessions, tool_total)

    return {
        "active_client_sessions": effective_sessions,
        "tool_calls": {
            "total": tool_total,
            "by_outcome": tool_by_outcome,
            "by_client": tool_by_client if not client_id else None,
            "by_tool": tool_by_name,
        },
        "auth_events": {
            "total": auth_total,
            "by_type": auth_by_type,
        },
        "http_requests": {
            "total": _counter_total(HTTP_REQUESTS_TOTAL),
            "by_status": _counter_by_label(HTTP_REQUESTS_TOTAL, "status"),
        },
        "admin_operations": {
            "total": admin_total,
            "by_outcome": admin_by_outcome,
        },
    }
