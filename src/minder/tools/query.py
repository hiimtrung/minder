from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from minder.config import MinderConfig
from minder.graph import GraphState, MinderGraph
from minder.store.error import ErrorStore
from minder.store.relational import RelationalStore


class QueryTools:
    def __init__(
        self,
        store: RelationalStore,
        config: MinderConfig,
        graph: MinderGraph | None = None,
        error_store: ErrorStore | None = None,
    ) -> None:
        self._store = store
        self._config = config
        self._graph = graph or MinderGraph(store, config)
        self._error_store = error_store or ErrorStore(store)

    async def minder_query(
        self,
        query: str,
        *,
        repo_path: str,
        session_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        repo_id: uuid.UUID | None = None,
        workflow_name: str | None = None,
        verification_payload: dict[str, Any] | None = None,
        max_attempts: int = 2,
    ) -> dict[str, Any]:
        state = GraphState(
            query=query,
            session_id=session_id,
            user_id=user_id,
            repo_id=repo_id,
            repo_path=repo_path,
            workflow_context={"workflow_name": workflow_name} if workflow_name else {},
            metadata={
                "verification_payload": verification_payload,
                "max_attempts": max_attempts,
            },
        )
        result = await self._graph.run(state)
        return {
            "answer": result.llm_output.get("text", ""),
            "sources": result.reasoning_output.get("sources", []),
            "workflow": result.workflow_context,
            "guard_result": result.guard_result,
            "verification_result": result.verification_result,
            "evaluation": result.evaluation,
            "provider": result.llm_output.get("provider"),
            "model": result.llm_output.get("model", result.llm_output.get("model_path")),
            "runtime": result.llm_output.get("runtime"),
            "transition_log": result.transition_log,
            "edge": result.metadata.get("edge"),
        }

    async def minder_search_code(
        self, query: str, *, repo_path: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        state = GraphState(query=query, repo_path=repo_path)
        retriever = self._graph._retriever
        state = retriever.run(state)
        return [
            {
                "path": doc["path"],
                "title": doc["title"],
                "score": doc["score"],
                "source_type": doc.get("doc_type", "unknown"),
            }
            for doc in state.retrieved_docs[:limit]
        ]

    async def minder_search_errors(
        self, query: str, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        return await self._error_store.search_errors(query, limit=limit)

    @staticmethod
    def discover_repo_files(repo_path: str) -> list[str]:
        return [str(path) for path in Path(repo_path).rglob("*") if path.is_file()]
