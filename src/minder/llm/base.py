from __future__ import annotations

from typing import Protocol

from minder.graph.state import GraphState


class LLMClient(Protocol):
    def generate(self, state: GraphState) -> dict[str, object]: ...
