"""Concurrency utilities for CPU-bound graph inference.

LLM inference (llama.cpp) is CPU-bound and can run for 5–30 s.  Running it
directly on the asyncio event loop starves every other in-flight request.

This module provides:
  - An asyncio.Semaphore that caps simultaneous LLM inferences.
  - ``run_in_thread`` — wraps a blocking callable in asyncio.to_thread with an
    optional timeout so the event loop stays responsive.
  - ``stream_sync_generator`` — converts a blocking sync generator (e.g.
    LLM token stream) into an async generator via a thread + queue, allowing
    real token-by-token streaming without blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Generator
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

_semaphore: asyncio.Semaphore | None = None
_max_concurrent: int = 1
_timeout_seconds: float = 120.0

# Dedicated thread pool for LLM / embedding inference.
# Using a bounded pool prevents runaway thread creation under load.
_INFERENCE_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="minder-inference")

T = TypeVar("T")

_SENTINEL = object()


def configure(*, max_concurrent: int = 1, timeout_seconds: float = 120.0) -> None:
    """Call once at startup to set inference concurrency and timeout budgets."""
    global _max_concurrent, _timeout_seconds, _semaphore
    _max_concurrent = max(1, max_concurrent)
    _timeout_seconds = max(10.0, timeout_seconds)
    _semaphore = asyncio.Semaphore(_max_concurrent)


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_max_concurrent)
    return _semaphore


async def run_in_thread(
    fn: Callable[..., T],
    /,
    *args: Any,
    timeout: float | None = None,
    use_llm_semaphore: bool = False,
) -> T:
    """Run a blocking callable in the inference thread pool.

    Args:
        fn: Blocking callable.
        *args: Positional arguments forwarded to fn.
        timeout: Maximum seconds to wait.  Defaults to the configured global
            timeout when ``use_llm_semaphore`` is True, otherwise no timeout.
        use_llm_semaphore: Acquire the global LLM concurrency semaphore before
            running.  Use this for actual LLM inference calls so we never run
            more than ``max_concurrent`` inferences simultaneously.
    """
    effective_timeout = timeout or (_timeout_seconds if use_llm_semaphore else None)

    async def _inner() -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_INFERENCE_POOL, fn, *args)

    if use_llm_semaphore:
        sem = _get_semaphore()
        try:
            async with sem:
                if effective_timeout:
                    return await asyncio.wait_for(_inner(), timeout=effective_timeout)
                return await _inner()
        except asyncio.TimeoutError:
            logger.warning("LLM inference timed out after %.0f s", effective_timeout)
            raise
    else:
        if effective_timeout:
            return await asyncio.wait_for(_inner(), timeout=effective_timeout)
        return await _inner()


async def stream_sync_generator(
    gen_fn: Callable[..., Generator[Any, None, None]],
    /,
    *args: Any,
    timeout: float | None = None,
    use_llm_semaphore: bool = True,
) -> AsyncGenerator[Any, None]:
    """Adapt a blocking sync generator into an async generator.

    The generator runs inside the inference thread pool so the asyncio event
    loop is never blocked.  Items are forwarded through an asyncio.Queue so
    consumers receive them as they are produced.

    Usage::

        async for event in stream_sync_generator(llm_node.stream, state):
            yield event
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=64)
    effective_timeout = timeout or (_timeout_seconds if use_llm_semaphore else None)

    def _producer() -> None:
        try:
            for item in gen_fn(*args):
                # Put items synchronously from the thread, waking up the consumer.
                asyncio.run_coroutine_threadsafe(queue.put(item), loop).result()
        except Exception as exc:
            asyncio.run_coroutine_threadsafe(queue.put(exc), loop).result()
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(_SENTINEL), loop).result()

    async def _generate() -> AsyncGenerator[Any, None]:
        future = loop.run_in_executor(_INFERENCE_POOL, _producer)
        deadline = (
            loop.time() + effective_timeout if effective_timeout else None
        )
        try:
            while True:
                remaining = (
                    max(0.1, deadline - loop.time()) if deadline else None
                )
                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=remaining
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "LLM stream timed out after %.0f s", effective_timeout
                    )
                    future.cancel()
                    return
                if item is _SENTINEL:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            # Drain queue to unblock any waiting producer thread.
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            try:
                await future
            except Exception:
                pass

    sem = _get_semaphore()
    if use_llm_semaphore:
        async with sem:
            async for item in _generate():
                yield item
    else:
        async for item in _generate():
            yield item
