from __future__ import annotations

from collections.abc import Generator
from typing import Protocol

from minder.graph.state import GraphState


class LLMClient(Protocol):
    def generate(self, state: GraphState) -> dict[str, object]: ...

    def stream_generate(
        self, state: GraphState
    ) -> Generator[dict[str, object], None, None]: ...
