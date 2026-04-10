"""OpenTelemetry tracing helpers for Minder.

The module uses a graceful-degradation pattern: it tries to import the
``opentelemetry`` packages at import time.  If they are not installed the
module falls back to a lightweight no-op implementation so the rest of the
codebase can import and call ``get_tracer`` / ``trace_async`` / ``start_span``
unconditionally without a hard dependency on the OTel SDK.

Installing the SDK is opt-in:
    uv add opentelemetry-api opentelemetry-sdk

The OTLP exporter is also optional:
    uv add opentelemetry-exporter-otlp-proto-grpc
"""
from __future__ import annotations

import functools
import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Callable, Iterator, TypeVar

_log = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# Try to import the real OTel SDK
# ---------------------------------------------------------------------------

try:
    from opentelemetry import trace as _otel_trace  # type: ignore[import-untyped]
    from opentelemetry.sdk.resources import Resource  # type: ignore[import-untyped]
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-untyped]
    from opentelemetry.sdk.trace.export import (  # type: ignore[import-untyped]
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover – OTel is optional
    _OTEL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Global tracer provider reference
# ---------------------------------------------------------------------------

_provider: Any = None  # TracerProvider | None


def _is_configured() -> bool:
    return _provider is not None


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def configure_tracing(
    service_name: str = "minder",
    service_version: str = "0.1.0",
    *,
    otlp_endpoint: str | None = None,
    console_export: bool = False,
) -> None:
    """Initialise the OTel tracer provider.

    Call once at server startup (from ``bootstrap/providers.py``).

    Args:
        service_name:     OTel ``service.name`` resource attribute.
        service_version:  OTel ``service.version`` resource attribute.
        otlp_endpoint:    gRPC OTLP collector endpoint, e.g.
                          ``"http://otel-collector:4317"``.  When *None* and
                          *console_export* is *False*, a no-op provider is used.
        console_export:   Emit spans to stdout (useful for local debugging).
    """
    global _provider  # noqa: PLW0603

    if not _OTEL_AVAILABLE:
        _log.info(
            "opentelemetry-sdk not installed — tracing disabled. "
            "Run `uv add opentelemetry-api opentelemetry-sdk` to enable."
        )
        return

    resource = Resource.create(
        {"service.name": service_name, "service.version": service_version}
    )
    provider = TracerProvider(resource=resource)

    if console_export:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    elif otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-untyped]
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
            )
        except ImportError:
            _log.warning(
                "opentelemetry-exporter-otlp-proto-grpc not installed; "
                "OTLP tracing export disabled."
            )

    _otel_trace.set_tracer_provider(provider)
    _provider = provider
    _log.info(
        "OTel tracing configured (service=%s, console=%s, otlp=%s).",
        service_name,
        console_export,
        otlp_endpoint,
    )


# ---------------------------------------------------------------------------
# No-op span context manager (fallback)
# ---------------------------------------------------------------------------


class _NoOpSpan:
    """Minimal span interface used when OTel is not available."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ARG002
        pass

    def record_exception(self, exc: BaseException) -> None:  # noqa: ARG002
        pass

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *_: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_tracer(name: str) -> Any:
    """Return an OTel tracer (or a minimal no-op tracer).

    The returned object supports ``tracer.start_as_current_span(name)`` and
    ``tracer.start_span(name)`` with the standard OTel API surface.
    """
    if _OTEL_AVAILABLE and _is_configured():
        return _otel_trace.get_tracer(name)
    return _NoOpTracer()


class _NoOpTracer:
    """No-op tracer returned when OTel SDK is absent or not configured."""

    @contextmanager
    def start_as_current_span(self, name: str, **_kwargs: Any) -> Iterator[_NoOpSpan]:  # noqa: ARG002
        yield _NoOpSpan()

    def start_span(self, name: str, **_kwargs: Any) -> _NoOpSpan:  # noqa: ARG002
        return _NoOpSpan()


@contextmanager
def start_span(name: str, tracer_name: str = "minder") -> Iterator[Any]:
    """Context manager that starts a named span (no-op if OTel unavailable)."""
    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(name) as span:
        yield span


@asynccontextmanager
async def async_span(name: str, tracer_name: str = "minder") -> AsyncIterator[Any]:
    """Async context manager that starts a named span."""
    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(name) as span:
        yield span


def trace_async(
    span_name: str | None = None,
    tracer_name: str = "minder",
) -> Callable[[F], F]:
    """Decorator that wraps an async function in an OTel span.

    Example::

        @trace_async("graph.retriever.run")
        async def run(self, state):
            ...
    """

    def decorator(fn: F) -> F:
        name = span_name or f"{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with async_span(name, tracer_name=tracer_name) as span:
                try:
                    result = await fn(*args, **kwargs)
                    return result
                except Exception as exc:
                    if hasattr(span, "record_exception"):
                        span.record_exception(exc)
                    raise

        return wrapper  # type: ignore[return-value]

    return decorator
