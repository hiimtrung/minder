from __future__ import annotations

from collections.abc import AsyncGenerator
import uuid
from pathlib import Path
from typing import Any

from minder.config import MinderConfig
from minder.embedding.local import LocalEmbeddingProvider
from minder.graph import GraphState, MinderGraph
from minder.graph.nodes.retriever import RetrieverNode
from minder.observability.metrics import (
    record_continuity_packet,
    record_query_prompt_render,
)
from minder.prompts import PromptRegistry
from minder.store.interfaces import IOperationalStore, IVectorStore
from minder.tools.graph import GraphTools
from minder.tools.ingest import IngestTools


class QueryTools:
    def __init__(
        self,
        store: IOperationalStore,
        config: MinderConfig,
        graph: MinderGraph | None = None,
        vector_store: IVectorStore | None = None,
        graph_tools: GraphTools | None = None,
    ) -> None:
        from minder.store.vector import VectorStore

        self._store = store
        self._config = config
        self._graph = graph or MinderGraph(store, config)
        self._vector_store = vector_store or VectorStore(store, store)
        self._embedding_provider = LocalEmbeddingProvider(
            config.embedding.model_path,
            dimensions=config.embedding.dimensions,
            runtime="auto",
        )
        self._ingest_tools = IngestTools(
            self._store,
            self._embedding_provider,
            vector_store=self._vector_store,
        )
        self._graph_tools = graph_tools

    async def minder_query(
        self,
        query: str,
        *,
        repo_path: str | None,
        session_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        repo_id: uuid.UUID | None = None,
        workflow_name: str | None = None,
        verification_payload: dict[str, Any] | None = None,
        max_attempts: int = 2,
        allowed_repo_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        project_name = Path(repo_path).name if repo_path else None
        if repo_path:
            await self._ingest_tools.minder_ingest_directory(
                repo_path, project=project_name
            )
        workflow_context: dict[str, Any] = (
            {"workflow_name": workflow_name} if workflow_name else {}
        )
        if self._graph_tools is not None and repo_path:
            cross_repo_context, cross_repo_graph = (
                await self._graph_tools.build_cross_repo_context(
                    query,
                    repo_path=repo_path,
                    repo_id=str(repo_id) if repo_id is not None else None,
                    repo_name=Path(repo_path).name,
                    allowed_repo_scopes=allowed_repo_scopes,
                )
            )
            if cross_repo_context:
                workflow_context["cross_repo_context"] = cross_repo_context
            if cross_repo_graph is not None:
                workflow_context["cross_repo_graph"] = cross_repo_graph
        query_prompt = await PromptRegistry.resolve_prompt_model(
            "query_reasoning",
            self._store,
        )
        state = GraphState(
            query=query,
            session_id=session_id,
            user_id=user_id,
            repo_id=repo_id,
            repo_path=repo_path,
            workflow_context=workflow_context,
            metadata={
                "verification_payload": verification_payload,
                "max_attempts": max_attempts,
                "project_name": project_name,
                "query_prompt_name": getattr(query_prompt, "name", "query_reasoning"),
                "query_prompt_template": getattr(query_prompt, "content_template", ""),
                "query_prompt_defaults": dict(
                    getattr(query_prompt, "defaults", {}) or {}
                ),
                "query_prompt_source": (
                    "builtin"
                    if bool(getattr(query_prompt, "is_builtin", False))
                    else "custom"
                ),
            },
        )
        result = await self._graph.run(state)
        record_continuity_packet("query")
        record_query_prompt_render(
            str(
                result.metadata.get(
                    "query_prompt_source",
                    state.metadata.get("query_prompt_source", "unknown"),
                )
            ),
            correction_retries=sum(
                1
                for item in result.transition_log
                if str(item.get("edge")) == "guard_failed"
            ),
        )
        return {
            "answer": result.llm_output.get("text", ""),
            "sources": result.reasoning_output.get("sources", []),
            "workflow": result.workflow_context,
            "guard_result": result.guard_result,
            "verification_result": result.verification_result,
            "evaluation": result.evaluation,
            "provider": result.llm_output.get("provider"),
            "model": result.llm_output.get(
                "model", result.llm_output.get("model_path")
            ),
            "runtime": result.llm_output.get("runtime"),
            "orchestration_runtime": result.metadata.get("orchestration_runtime"),
            "transition_log": result.transition_log,
            "edge": result.metadata.get("edge"),
            "cross_repo_graph": result.workflow_context.get("cross_repo_graph"),
        }

    async def minder_query_stream(
        self,
        query: str,
        *,
        repo_path: str | None,
        session_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        repo_id: uuid.UUID | None = None,
        workflow_name: str | None = None,
        verification_payload: dict[str, Any] | None = None,
        max_attempts: int = 2,
        allowed_repo_scopes: list[str] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        project_name = Path(repo_path).name if repo_path else None
        if repo_path:
            await self._ingest_tools.minder_ingest_directory(
                repo_path, project=project_name
            )
        workflow_context: dict[str, Any] = (
            {"workflow_name": workflow_name} if workflow_name else {}
        )
        if self._graph_tools is not None and repo_path:
            cross_repo_context, cross_repo_graph = (
                await self._graph_tools.build_cross_repo_context(
                    query,
                    repo_path=repo_path,
                    repo_id=str(repo_id) if repo_id is not None else None,
                    repo_name=Path(repo_path).name,
                    allowed_repo_scopes=allowed_repo_scopes,
                )
            )
            if cross_repo_context:
                workflow_context["cross_repo_context"] = cross_repo_context
            if cross_repo_graph is not None:
                workflow_context["cross_repo_graph"] = cross_repo_graph
        query_prompt = await PromptRegistry.resolve_prompt_model(
            "query_reasoning",
            self._store,
        )
        state = GraphState(
            query=query,
            session_id=session_id,
            user_id=user_id,
            repo_id=repo_id,
            repo_path=repo_path,
            workflow_context=workflow_context,
            metadata={
                "verification_payload": verification_payload,
                "max_attempts": max_attempts,
                "project_name": project_name,
                "query_prompt_name": getattr(query_prompt, "name", "query_reasoning"),
                "query_prompt_template": getattr(query_prompt, "content_template", ""),
                "query_prompt_defaults": dict(
                    getattr(query_prompt, "defaults", {}) or {}
                ),
                "query_prompt_source": (
                    "builtin"
                    if bool(getattr(query_prompt, "is_builtin", False))
                    else "custom"
                ),
            },
        )

        async for event in self._graph.stream(state):
            if str(event.get("type")) == "final":
                final_state = event.get("state")
                if isinstance(final_state, GraphState):
                    result = self._result_from_state(final_state)
                    record_continuity_packet("query")
                    record_query_prompt_render(
                        str(
                            final_state.metadata.get(
                                "query_prompt_source",
                                state.metadata.get("query_prompt_source", "unknown"),
                            )
                        ),
                        correction_retries=sum(
                            1
                            for item in final_state.transition_log
                            if str(item.get("edge")) == "guard_failed"
                        ),
                    )
                    yield {"type": "final", "payload": result}
                continue
            yield event

    def _result_from_state(self, result: GraphState) -> dict[str, Any]:
        return {
            "answer": result.llm_output.get("text", ""),
            "sources": result.reasoning_output.get("sources", []),
            "workflow": result.workflow_context,
            "guard_result": result.guard_result,
            "verification_result": result.verification_result,
            "evaluation": result.evaluation,
            "provider": result.llm_output.get("provider"),
            "model": result.llm_output.get(
                "model", result.llm_output.get("model_path")
            ),
            "runtime": result.llm_output.get("runtime"),
            "orchestration_runtime": result.metadata.get("orchestration_runtime"),
            "transition_log": result.transition_log,
            "edge": result.metadata.get("edge"),
            "cross_repo_graph": result.workflow_context.get("cross_repo_graph"),
        }

    async def minder_search_code(
        self, query: str, *, repo_path: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        await self._ingest_tools.minder_ingest_directory(
            repo_path, project=Path(repo_path).name
        )
        project_name = Path(repo_path).name
        semantic_code_hits = await self._vector_store.search_documents(
            self._embedding_provider.embed(query),
            project=project_name,
            doc_types={"code"},
            limit=limit,
            score_threshold=0.0,
        )
        if semantic_code_hits:
            return [
                {
                    "path": doc["path"],
                    "title": doc["title"],
                    "score": doc["score"],
                    "source_type": doc.get("doc_type", "unknown"),
                }
                for doc in semantic_code_hits[:limit]
            ]

        state = GraphState(
            query=query,
            repo_path=repo_path,
            metadata={"project_name": project_name},
        )
        retriever = RetrieverNode(
            top_k=limit,
            embedding_provider=self._embedding_provider,
            vector_store=self._vector_store,
            score_threshold=self._config.retrieval.similarity_threshold,
        )
        state = await retriever.run(state)
        code_docs = [
            doc for doc in state.retrieved_docs if doc.get("doc_type") == "code"
        ]
        docs_to_return = code_docs or state.retrieved_docs
        return [
            {
                "path": doc["path"],
                "title": doc["title"],
                "score": doc["score"],
                "source_type": doc.get("doc_type", "unknown"),
            }
            for doc in docs_to_return[:limit]
        ]

    async def minder_search_errors(
        self, query: str, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        return await self._store.search_errors(query, limit=limit)

    @staticmethod
    def discover_repo_files(repo_path: str) -> list[str]:
        return [str(path) for path in Path(repo_path).rglob("*") if path.is_file()]
