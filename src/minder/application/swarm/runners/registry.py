"""Runner registry — provider-style factory (mirrors llm/factory.py)."""

from __future__ import annotations

from minder.application.swarm.runners.acp import AcpRunner
from minder.application.swarm.runners.base import AgentRunner, MockRunner
from minder.application.swarm.runners.vendors import (
    AntigravityRunner,
    ClaudeRunner,
    CodexRunner,
)

_RUNNERS: dict[str, type] = {
    "claude": ClaudeRunner,
    "codex": CodexRunner,
    "antigravity": AntigravityRunner,
    "acp": AcpRunner,
    "mock": MockRunner,
}


def list_runtimes() -> list[str]:
    return sorted(_RUNNERS.keys())


def create_runner(runtime: str) -> AgentRunner:
    cls = _RUNNERS.get(runtime)
    if cls is None:
        raise ValueError(
            f"unknown runtime: {runtime!r}. Known: {', '.join(list_runtimes())}"
        )
    return cls()  # type: ignore[return-value]
