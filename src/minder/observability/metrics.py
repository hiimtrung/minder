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
    [
        "tool_name",
        "outcome",
    ],  # client_id is high-cardinality → stored in audit DB, not here
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
    ["event_type", "outcome"],  # client_id is high-cardinality → stored in audit DB
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
# Continuity quality metrics
# ---------------------------------------------------------------------------

CONTINUITY_PACKETS_TOTAL = Counter(
    "minder_continuity_packets_total",
    "Total continuity packets emitted by continuity-aware surfaces.",
    ["source"],
    registry=REGISTRY,
)

CONTINUITY_RECALLS_TOTAL = Counter(
    "minder_continuity_recalls_total",
    "Total continuity recall operations grouped by synthesis provider.",
    ["provider"],
    registry=REGISTRY,
)

CONTINUITY_STEP_COMPATIBILITY = Histogram(
    "minder_continuity_step_compatibility",
    "Observed workflow-step compatibility scores for continuity-aware retrieval.",
    buckets=(0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5),
    registry=REGISTRY,
)

CONTINUITY_SKILL_QUALITY = Histogram(
    "minder_continuity_skill_quality",
    "Observed quality scores for workflow-aware skill retrieval.",
    buckets=(0.0, 0.1, 0.25, 0.5, 0.75, 1.0),
    registry=REGISTRY,
)

CONTINUITY_QUERY_PROMPTS_TOTAL = Counter(
    "minder_continuity_query_prompts_total",
    "Total query prompt renders grouped by prompt source.",
    ["source"],
    registry=REGISTRY,
)

CONTINUITY_CORRECTION_RETRIES_TOTAL = Counter(
    "minder_continuity_correction_retries_total",
    "Total corrective retries triggered by continuity/workflow contract failures.",
    ["failure_kind"],
    registry=REGISTRY,
)

CONTINUITY_GATES_TOTAL = Counter(
    "minder_continuity_gates_total",
    "Total continuity gate evaluations grouped by outcome.",
    ["outcome"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def record_tool_call(
    tool_name: str,
    outcome: str,
    duration_seconds: float,
    client_id: str = "unknown",  # kept for API compat; stored in audit DB, not Prometheus label
) -> None:
    """Record a tool invocation outcome and latency."""
    TOOL_CALLS_TOTAL.labels(tool_name=tool_name, outcome=outcome).inc()
    TOOL_CALL_DURATION.labels(tool_name=tool_name).observe(duration_seconds)


async def record_auth_event(
    event_type: str,
    outcome: str,
    client_id: str = "unknown",
    store: "IOperationalStore | None" = None,
) -> None:
    """Record an auth/session lifecycle event.

    Increments the Prometheus counter (synchronous) then writes an audit log
    entry to the store (async, best-effort — failures are swallowed).
    """
    AUTH_EVENTS_TOTAL.labels(event_type=event_type, outcome=outcome).inc()

    if store is not None:
        try:
            await store.create_audit_log(
                actor_type="auth",
                actor_id=client_id,
                event_type=event_type,
                resource_type="session",
                resource_id=client_id,
                outcome=outcome,
                audit_metadata={"client_id": client_id},
            )
        except Exception:  # noqa: BLE001
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
    HTTP_REQUEST_DURATION.labels(method=method, path_template=path_template).observe(
        duration_seconds
    )


def record_continuity_packet(source: str) -> None:
    CONTINUITY_PACKETS_TOTAL.labels(source=source or "unknown").inc()


def record_continuity_recall(*, provider: str, step_compatibility: float) -> None:
    CONTINUITY_RECALLS_TOTAL.labels(provider=provider or "unknown").inc()
    CONTINUITY_STEP_COMPATIBILITY.observe(step_compatibility)


def record_continuity_skill_recall(
    *, step_compatibility: float, quality_score: float
) -> None:
    CONTINUITY_STEP_COMPATIBILITY.observe(step_compatibility)
    CONTINUITY_SKILL_QUALITY.observe(max(quality_score, 0.0))


def record_query_prompt_render(source: str, *, correction_retries: int = 0) -> None:
    CONTINUITY_QUERY_PROMPTS_TOTAL.labels(source=source or "unknown").inc()
    if correction_retries > 0:
        CONTINUITY_CORRECTION_RETRIES_TOTAL.labels(
            failure_kind="workflow_contract"
        ).inc(correction_retries)


def record_continuity_gate(outcome: str) -> None:
    CONTINUITY_GATES_TOTAL.labels(outcome=outcome or "unknown").inc()


async def record_admin_operation(
    operation: str,
    outcome: str,
    actor_id: str = "unknown",
    store: IOperationalStore | None = None,
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
                audit_metadata={"operation": operation},
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
    counter: Counter, filter_label: str | None = None, filter_value: str | None = None
) -> float:
    """Sum all label-value combinations of a Counter, optionally filtering."""
    total = 0.0
    label_names = counter._labelnames  # noqa: SLF001
    filter_idx = (
        label_names.index(filter_label) if filter_label in label_names else None
    )

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
    filter_value: str | None = None,
) -> dict[str, float]:
    """Aggregate a Counter by a single label, optionally filtering."""
    label_names: tuple[str, ...] = counter._labelnames  # noqa: SLF001
    if label_name not in label_names:
        return {}

    idx = label_names.index(label_name)
    filter_idx = (
        label_names.index(filter_label) if filter_label in label_names else None
    )

    result: dict[str, float] = {}
    for label_tuple, child in counter._metrics.items():  # noqa: SLF001
        if filter_idx is not None and filter_value:
            if label_tuple[filter_idx] != filter_value:
                continue
        key = label_tuple[idx]
        result[key] = (
            result.get(key, 0.0) + cast(Any, child)._value.get()
        )  # noqa: SLF001
    return result


def _histogram_average(histogram: Histogram) -> float:
    total = 0.0
    count = 0.0
    for metric in histogram.collect():
        for sample in metric.samples:
            if sample.name.endswith("_sum"):
                total = float(sample.value)
            elif sample.name.endswith("_count"):
                count = float(sample.value)
    if count <= 0:
        return 0.0
    return round(total / count, 4)


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
        actor_id=client_id, event_type="tool_call", outcome=outcome, group_by="outcome"
    )
    tool_by_client = await store.get_audit_summary(
        event_type="tool_call",
        outcome=outcome,
        group_by="audit_metadata.client_id",  # This depends on Mongo/SQL support for nested fields
    )
    tool_by_name = await store.get_audit_summary(
        actor_id=client_id,
        event_type="tool_call",
        outcome=outcome,
        group_by="tool_name",
    )
    tool_total = sum(tool_by_outcome.values())

    # 2. Auth Events (we combine tool_calls and auth_events for a "unified" view if needed)
    auth_by_type = await store.get_audit_summary(
        actor_id=client_id,
        event_type=event_type,
        outcome=outcome,
        group_by="event_type",
    )
    auth_total = sum(auth_by_type.values())

    # 3. Admin Ops
    admin_by_outcome = await store.get_audit_summary(
        event_type="admin_op", outcome=outcome, group_by="outcome"
    )
    admin_total = sum(admin_by_outcome.values())

    # Runtime stats from Prometheus (Fallback/Ephemeral)
    effective_sessions = (
        active_sessions
        if active_sessions is not None
        else ACTIVE_CLIENT_SESSIONS._value.get()
    )

    logger.info(
        "Serving persistent metrics summary: sessions=%s, tool_calls=%s",
        effective_sessions,
        tool_total,
    )

    return {
        "active_client_sessions": effective_sessions,
        "tool_calls": {
            "total": tool_total,
            "by_outcome": tool_by_outcome,
            "by_client": tool_by_client,
            "by_name": tool_by_name,
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
        "continuity_quality": {
            "packets_emitted_total": _counter_total(CONTINUITY_PACKETS_TOTAL),
            "packets_by_source": _counter_by_label(CONTINUITY_PACKETS_TOTAL, "source"),
            "recalls_total": _counter_total(CONTINUITY_RECALLS_TOTAL),
            "recalls_by_provider": _counter_by_label(
                CONTINUITY_RECALLS_TOTAL, "provider"
            ),
            "average_step_compatibility": _histogram_average(
                CONTINUITY_STEP_COMPATIBILITY
            ),
            "average_skill_quality": _histogram_average(CONTINUITY_SKILL_QUALITY),
            "query_prompts_by_source": _counter_by_label(
                CONTINUITY_QUERY_PROMPTS_TOTAL, "source"
            ),
            "correction_retries_total": _counter_total(
                CONTINUITY_CORRECTION_RETRIES_TOTAL
            ),
            "gates_by_outcome": _counter_by_label(CONTINUITY_GATES_TOTAL, "outcome"),
        },
    }
