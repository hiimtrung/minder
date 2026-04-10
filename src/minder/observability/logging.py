"""Structured JSON logging and request correlation-ID middleware for Minder."""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

# ---------------------------------------------------------------------------
# Correlation ID context variable
# ---------------------------------------------------------------------------

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Return the correlation ID bound to the current async task."""
    return _correlation_id.get("")


def set_correlation_id(cid: str) -> None:
    """Bind a correlation ID to the current async task."""
    _correlation_id.set(cid)


# ---------------------------------------------------------------------------
# JSON log formatter
# ---------------------------------------------------------------------------

_RESERVED_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }
)


class JsonFormatter(logging.Formatter):
    """Formats log records as a single-line JSON object.

    The emitted keys are always:
        timestamp   ISO-8601 UTC
        level       log level name
        logger      logger name
        message     formatted message
        correlation_id  current request ID (empty string if not set)

    Any extra fields set via ``extra=`` on the log call are merged in.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        record.message = record.getMessage()
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
            "correlation_id": get_correlation_id() or record.__dict__.get("correlation_id", ""),
        }
        # Merge caller-supplied extra keys
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                payload.setdefault(key, value)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_json_logging(level: str = "INFO") -> None:
    """Replace the root logger's handlers with a JSON-emitting stream handler.

    Call this once at server startup; subsequent ``logging.getLogger(…)``
    calls will inherit the formatter automatically.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


# ---------------------------------------------------------------------------
# Starlette ASGI correlation-ID middleware
# ---------------------------------------------------------------------------


class CorrelationIdMiddleware:
    """ASGI middleware that assigns a unique correlation ID to every request.

    The ID is taken from the incoming ``X-Correlation-ID`` header when
    present, or generated fresh as a UUID4 hex string.  It is:

    * Stored in the ``correlation_id`` ContextVar (readable via
      :func:`get_correlation_id` anywhere in the same async task).
    * Added to the response as the ``X-Correlation-ID`` header.
    """

    def __init__(self, app: "ASGIApp") -> None:
        self.app = app

    async def __call__(
        self, scope: "Scope", receive: "Receive", send: "Send"
    ) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract or generate a correlation ID
        headers = dict(scope.get("headers", []))
        raw_cid = headers.get(b"x-correlation-id", b"")
        cid = raw_cid.decode("latin-1", errors="replace") if raw_cid else uuid.uuid4().hex
        set_correlation_id(cid)

        async def send_with_correlation(message: dict) -> None:  # type: ignore[type-arg]
            if message["type"] == "http.response.start":
                # Append the correlation-ID header to the response
                extra = [(b"x-correlation-id", cid.encode())]
                message = {**message, "headers": list(message.get("headers", [])) + extra}
            await send(message)

        await self.app(scope, receive, send_with_correlation)


# ---------------------------------------------------------------------------
# HTTP request/response access-log middleware
# ---------------------------------------------------------------------------


class AccessLogMiddleware:
    """ASGI middleware that emits a structured access log entry per request."""

    def __init__(self, app: "ASGIApp", logger_name: str = "minder.access") -> None:
        self.app = app
        self._log = logging.getLogger(logger_name)

    async def __call__(
        self, scope: "Scope", receive: "Receive", send: "Send"
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = [0]

        async def capture_status(message: dict) -> None:  # type: ignore[type-arg]
            if message["type"] == "http.response.start":
                status_code[0] = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            elapsed = time.perf_counter() - start
            method = scope.get("method", "")
            path = scope.get("path", "")
            self._log.info(
                "%s %s %s",
                method,
                path,
                status_code[0],
                extra={
                    "http_method": method,
                    "http_path": path,
                    "http_status": status_code[0],
                    "duration_ms": round(elapsed * 1000, 2),
                },
            )
