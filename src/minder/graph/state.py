from __future__ import annotations

from copy import deepcopy
import operator
import uuid
from typing import Annotated, Any, TypedDict


def merge_dicts(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    res = dict(a or {})
    res.update(b or {})
    return res


class GraphStateSchema(TypedDict, total=False):
    query: str
    session_id: uuid.UUID | None
    user_id: uuid.UUID | None
    repo_id: uuid.UUID | None
    repo_path: str | None
    plan: dict[str, Any]
    retrieved_docs: Annotated[list[dict[str, Any]], operator.add]
    reranked_docs: Annotated[list[dict[str, Any]], operator.add]
    workflow_context: dict[str, Any]
    reasoning_output: dict[str, Any]
    llm_output: dict[str, Any]
    guard_result: dict[str, Any]
    verification_result: dict[str, Any]
    evaluation: dict[str, Any]
    agent_outputs: Annotated[list[dict[str, Any]], operator.add]
    transition_log: Annotated[list[dict[str, Any]], operator.add]
    retry_count: int
    metadata: Annotated[dict[str, Any], merge_dicts]
    chat_history: list[dict[str, Any]]


class GraphState(dict[str, Any]):
    def __init__(self, **kwargs: Any) -> None:
        data = self._defaults()
        data.update(kwargs)
        super().__init__(data)

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - standard attribute behavior
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    @classmethod
    def model_validate(cls, value: GraphState | dict[str, Any] | None) -> GraphState:
        if isinstance(value, cls):
            return value
        data = cls._defaults()
        if value:
            data.update(dict(value))
        return cls(**data)

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        del mode
        return dict(self)

    def model_copy(self, *, deep: bool = False) -> GraphState:
        data = deepcopy(dict(self)) if deep else dict(self)
        return GraphState(**data)

    @staticmethod
    def _defaults() -> dict[str, Any]:
        return {
            "query": "",
            "session_id": None,
            "user_id": None,
            "repo_id": None,
            "repo_path": None,
            "plan": {},
            "retrieved_docs": [],
            "reranked_docs": [],
            "workflow_context": {},
            "reasoning_output": {},
            "llm_output": {},
            "guard_result": {},
            "verification_result": {},
            "evaluation": {},
            "agent_outputs": [],
            "transition_log": [],
            "retry_count": 0,
            "metadata": {},
            "chat_history": [],
        }
