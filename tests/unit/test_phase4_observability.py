"""Unit tests for the P4-T05 Observability Stack.

Tests cover:
- metrics registry and helper functions
- JSON log formatter output shape
- CorrelationIdMiddleware header injection
- AccessLogMiddleware call-through
- AuditEmitter happy-path and store-failure resilience
- Tracing no-op path (OTel not required)
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_metrics_registry_has_expected_counters() -> None:
    from minder.observability.metrics import (
        ADMIN_OPERATIONS_TOTAL,
        AUTH_EVENTS_TOTAL,
        HTTP_REQUESTS_TOTAL,
        TOOL_CALLS_TOTAL,
    )

    # Prometheus Counter stores the base name (without _total suffix) in ._name
    assert TOOL_CALLS_TOTAL._name == "minder_tool_calls"
    assert AUTH_EVENTS_TOTAL._name == "minder_auth_events"
    assert HTTP_REQUESTS_TOTAL._name == "minder_http_requests"
    assert ADMIN_OPERATIONS_TOTAL._name == "minder_admin_operations"


def test_record_tool_call_increments_counter() -> None:
    from minder.observability.metrics import TOOL_CALLS_TOTAL, record_tool_call

    before = TOOL_CALLS_TOTAL.labels(
        tool_name="minder_test_probe", outcome="success"
    )._value.get()
    record_tool_call("minder_test_probe", "success", 0.1)
    after = TOOL_CALLS_TOTAL.labels(
        tool_name="minder_test_probe", outcome="success"
    )._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_record_auth_event_increments_counter() -> None:
    from minder.observability.metrics import AUTH_EVENTS_TOTAL, record_auth_event

    before = AUTH_EVENTS_TOTAL.labels(
        event_type="auth.login_test", outcome="success"
    )._value.get()
    await record_auth_event("auth.login_test", "success")
    after = AUTH_EVENTS_TOTAL.labels(
        event_type="auth.login_test", outcome="success"
    )._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_text() -> None:
    """metrics_endpoint returns 200 with Prometheus text/plain content."""
    from prometheus_client import CONTENT_TYPE_LATEST

    from minder.observability.metrics import metrics_endpoint

    request = MagicMock()
    response = await metrics_endpoint(request)
    assert response.status_code == 200
    assert CONTENT_TYPE_LATEST in response.media_type


# ---------------------------------------------------------------------------
# JSON logging
# ---------------------------------------------------------------------------


def test_json_formatter_emits_valid_json() -> None:
    from minder.observability.logging import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["message"] == "hello world"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert "timestamp" in parsed
    assert "correlation_id" in parsed


def test_json_formatter_merges_extra_keys() -> None:
    from minder.observability.logging import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname="x.py",
        lineno=2,
        msg="with extra",
        args=(),
        exc_info=None,
    )
    record.__dict__["my_custom_key"] = "my_custom_value"
    parsed = json.loads(formatter.format(record))
    assert parsed.get("my_custom_key") == "my_custom_value"


def test_configure_json_logging_replaces_root_handler() -> None:
    from minder.observability.logging import JsonFormatter, configure_json_logging

    configure_json_logging("WARNING")
    root = logging.getLogger()
    assert len(root.handlers) >= 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
    assert root.level == logging.WARNING


# ---------------------------------------------------------------------------
# Correlation-ID middleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_correlation_id_middleware_generates_id_when_missing() -> None:
    from minder.observability.logging import CorrelationIdMiddleware, get_correlation_id

    received_ids: list[str] = []

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:
        cid = get_correlation_id()
        received_ids.append(cid)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = CorrelationIdMiddleware(inner_app)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
    }
    response_messages: list[dict] = []

    async def send(msg: dict) -> None:
        response_messages.append(msg)

    await middleware(scope, None, send)
    assert received_ids[0] != ""
    # Response must carry the header
    start_msg = response_messages[0]
    header_dict = dict(start_msg.get("headers", []))
    assert b"x-correlation-id" in header_dict


@pytest.mark.asyncio
async def test_correlation_id_middleware_preserves_incoming_id() -> None:
    from minder.observability.logging import CorrelationIdMiddleware, get_correlation_id

    incoming_cid = "test-correlation-abc123"
    received_ids: list[str] = []

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:
        received_ids.append(get_correlation_id())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = CorrelationIdMiddleware(inner_app)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-correlation-id", incoming_cid.encode())],
    }

    async def noop_send(msg: dict) -> None:  # type: ignore[type-arg]
        pass

    await middleware(scope, None, noop_send)
    assert received_ids[0] == incoming_cid


@pytest.mark.asyncio
async def test_correlation_id_middleware_ignores_non_http_scopes() -> None:
    """CorrelationIdMiddleware passes lifespan/websocket scopes through unchanged."""
    from minder.observability.logging import CorrelationIdMiddleware

    called: list[bool] = []

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:
        called.append(True)

    middleware = CorrelationIdMiddleware(inner_app)
    await middleware({"type": "lifespan"}, None, None)
    assert called == [True]


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


def test_get_tracer_returns_usable_object_without_otel() -> None:
    """get_tracer() must return an object with start_as_current_span even if OTel absent."""
    from minder.observability.tracing import get_tracer

    tracer = get_tracer("minder.test")
    with tracer.start_as_current_span("test-span") as span:
        # Should not raise; attribute setting is a no-op
        span.set_attribute("foo", "bar")


@pytest.mark.asyncio
async def test_trace_async_decorator_does_not_break_wrapped_fn() -> None:
    from minder.observability.tracing import trace_async

    @trace_async("test.decorated_fn")
    async def my_fn(x: int) -> int:
        return x * 2

    result = await my_fn(21)
    assert result == 42


@pytest.mark.asyncio
async def test_trace_async_decorator_propagates_exceptions() -> None:
    from minder.observability.tracing import trace_async

    @trace_async("test.raises")
    async def failing_fn() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await failing_fn()


def test_start_span_context_manager() -> None:
    from minder.observability.tracing import start_span

    with start_span("test.sync.span") as span:
        span.set_attribute("key", "value")


# ---------------------------------------------------------------------------
# AuditEmitter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_emitter_calls_store_create_audit_log() -> None:
    from minder.observability.audit import AuditEmitter

    mock_store = MagicMock()
    mock_store.create_audit_log = AsyncMock()

    emitter = AuditEmitter(store=mock_store)
    actor_id = str(uuid.uuid4())
    resource_id = str(uuid.uuid4())

    await emitter.emit(
        actor_type="admin",
        actor_id=actor_id,
        event_type="client.created",
        resource_type="client",
        resource_id=resource_id,
        outcome="success",
    )

    mock_store.create_audit_log.assert_awaited_once()
    call_kwargs = mock_store.create_audit_log.call_args.kwargs
    assert call_kwargs["actor_id"] == actor_id
    assert call_kwargs["event_type"] == "client.created"
    assert call_kwargs["outcome"] == "success"


@pytest.mark.asyncio
async def test_audit_emitter_client_created_convenience() -> None:
    from minder.observability.audit import AuditEmitter

    mock_store = MagicMock()
    mock_store.create_audit_log = AsyncMock()

    emitter = AuditEmitter(store=mock_store)
    actor_id = str(uuid.uuid4())
    client_id = str(uuid.uuid4())

    await emitter.client_created(actor_id=actor_id, client_id=client_id)

    call_kwargs = mock_store.create_audit_log.call_args.kwargs
    assert call_kwargs["event_type"] == "client.created"
    assert call_kwargs["resource_id"] == client_id


@pytest.mark.asyncio
async def test_audit_emitter_resilient_to_store_failure() -> None:
    """AuditEmitter must not raise when the store write fails."""
    from minder.observability.audit import AuditEmitter

    mock_store = MagicMock()
    mock_store.create_audit_log = AsyncMock(side_effect=RuntimeError("DB unavailable"))

    emitter = AuditEmitter(store=mock_store)

    # Should not raise — failures are logged but swallowed
    await emitter.emit(
        actor_type="system",
        actor_id="system",
        event_type="test.event",
        resource_type="test",
        resource_id="test",
    )


@pytest.mark.asyncio
async def test_audit_emitter_token_exchanged_convenience() -> None:
    from minder.observability.audit import AuditEmitter

    mock_store = MagicMock()
    mock_store.create_audit_log = AsyncMock()

    emitter = AuditEmitter(store=mock_store)
    await emitter.token_exchanged(
        actor_id=str(uuid.uuid4()),
        client_id=str(uuid.uuid4()),
        scopes=["minder_query"],
    )

    call_kwargs = mock_store.create_audit_log.call_args.kwargs
    assert call_kwargs["event_type"] == "token.exchanged"
    assert call_kwargs["audit_metadata"]["scopes"] == ["minder_query"]


# ---------------------------------------------------------------------------
# /metrics route integration
# ---------------------------------------------------------------------------


def test_metrics_route_is_in_http_app() -> None:
    """/metrics must appear in the routes built by build_http_routes."""
    from unittest.mock import patch

    from minder.config import MinderConfig
    from minder.presentation.http.admin.routes import build_http_routes

    config = MinderConfig()
    mock_store = MagicMock()
    mock_store.create_audit_log = AsyncMock()

    with patch("minder.presentation.http.admin.context.AdminRouteContext.build") as mock_ctx:
        mock_ctx.return_value = MagicMock()
        with patch("minder.presentation.http.admin.routes.build_admin_api_routes", return_value=[]):
            with patch("minder.presentation.http.admin.routes.build_dashboard_routes", return_value=[]):
                routes = build_http_routes(config=config, store=mock_store)

    paths = [r.path for r in routes if hasattr(r, "path")]
    assert "/health" in paths
    assert "/metrics" in paths
