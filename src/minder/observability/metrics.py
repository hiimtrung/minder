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
    ["tool_name", "outcome"],  # outcome: success | error | denied
    registry=REGISTRY,
)

TOOL_CALL_DURATION = Histogram(
    "minder_tool_call_duration_seconds",
    "MCP tool call latency in seconds.",
    ["tool_name"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Auth / session metrics
# ---------------------------------------------------------------------------

AUTH_EVENTS_TOTAL = Counter(
    "minder_auth_events_total",
    "Total number of authentication and authorisation events.",
    ["event_type", "outcome"],  # event_type: login | token_exchange | key_revoke | …
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


def record_tool_call(tool_name: str, outcome: str, duration_seconds: float) -> None:
    """Record a completed tool call (outcome: 'success' | 'error' | 'denied')."""
    TOOL_CALLS_TOTAL.labels(tool_name=tool_name, outcome=outcome).inc()
    TOOL_CALL_DURATION.labels(tool_name=tool_name).observe(duration_seconds)


def record_auth_event(event_type: str, outcome: str) -> None:
    """Record an auth/session lifecycle event."""
    AUTH_EVENTS_TOTAL.labels(event_type=event_type, outcome=outcome).inc()


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


def record_admin_operation(operation: str, outcome: str) -> None:
    """Record an admin API operation (outcome: 'success' | 'error')."""
    ADMIN_OPERATIONS_TOTAL.labels(operation=operation, outcome=outcome).inc()


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


def _counter_total(counter: Counter) -> float:
    """Sum all label-value combinations of a Counter."""
    total = 0.0
    for child in counter._metrics.values():  # noqa: SLF001
        total += cast(Any, child)._value.get()  # noqa: SLF001
    return total


def _counter_by_label(counter: Counter, label_name: str) -> dict[str, float]:
    """Aggregate a Counter by a single label, returning {label_value: total}."""
    label_names: tuple[str, ...] = counter._labelnames  # noqa: SLF001
    if label_name not in label_names:
        return {}
    idx = label_names.index(label_name)
    result: dict[str, float] = {}
    for label_tuple, child in counter._metrics.items():  # noqa: SLF001
        key = label_tuple[idx]
        result[key] = result.get(key, 0.0) + cast(Any, child)._value.get()  # noqa: SLF001
    return result


def get_metrics_summary() -> dict[str, Any]:
    """Return a lightweight JSON-serialisable snapshot of key runtime metrics.

    Reads directly from the in-process Prometheus registry — no scrape needed.
    All values are floats; counters reflect the totals since process start.
    """
    return {
        "active_client_sessions": ACTIVE_CLIENT_SESSIONS._value.get(),  # noqa: SLF001
        "tool_calls": {
            "total": _counter_total(TOOL_CALLS_TOTAL),
            "by_outcome": _counter_by_label(TOOL_CALLS_TOTAL, "outcome"),
        },
        "auth_events": {
            "total": _counter_total(AUTH_EVENTS_TOTAL),
            "by_type": _counter_by_label(AUTH_EVENTS_TOTAL, "event_type"),
        },
        "http_requests": {
            "total": _counter_total(HTTP_REQUESTS_TOTAL),
            "by_status": _counter_by_label(HTTP_REQUESTS_TOTAL, "status"),
        },
        "admin_operations": {
            "total": _counter_total(ADMIN_OPERATIONS_TOTAL),
            "by_outcome": _counter_by_label(ADMIN_OPERATIONS_TOTAL, "outcome"),
        },
    }
