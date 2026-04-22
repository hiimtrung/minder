"""Session-wide test isolation.

The developer `.env` at the repo root (used by `minder serve` locally) points
at real infrastructure — Milvus, MongoDB, a local llama.cpp model file, etc.
When pytest imports `MinderConfig()` it transparently merges that `.env` into
config, and several integration tests then try to *actually* connect to those
services and hang until the job-level timeout. This module scrubs those
variables for the duration of the test session so every fixture that calls
`MinderConfig()` observes the documented hermetic defaults instead.

Tests that explicitly want a specific provider still set it on the config
object or via `env = os.environ.copy(); env["MINDER_..."] = "..."` for
subprocess children — `os.environ.copy()` captures the scrubbed environment,
so their subprocess inherits clean defaults plus whatever the test needs.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_minder_env_from_dotenv() -> Iterator[None]:
    """Strip MINDER_* env vars that a developer `.env` may have injected."""
    removed: dict[str, str] = {}
    for key in list(os.environ):
        if key.startswith("MINDER_"):
            removed[key] = os.environ.pop(key)
    
    # Force mock modes for tests to save RAM and time
    os.environ["MINDER_EMBEDDING__RUNTIME"] = "mock"
    os.environ["MINDER_LLM__LITERT_BACKEND"] = "mock"
    os.environ["MINDER_VECTOR_STORE__PROVIDER"] = "memory"
    
    try:
        yield
    finally:
        os.environ.update(removed)
