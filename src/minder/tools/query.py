from __future__ import annotations

from collections.abc import AsyncGenerator
import uuid
from pathlib import Path
from typing import Any

from minder.config import MinderConfig
from minder.context_compactor import HistoryCompactor
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
        self._graph = graph or MinderGraph(store, config, graph_tools=graph_tools)
        self._vector_store = vector_store or VectorStore(store, store)
        self._embedding_provider = LocalEmbeddingProvider(
            llama_cpp_model_repo=config.embedding.llama_cpp_model_repo,
            llama_cpp_model_file=config.embedding.llama_cpp_model_file,
            dimensions=config.embedding.dimensions,
            runtime=config.embedding.runtime,
        )
        self._ingest_tools = IngestTools(
            self._store,
            self._embedding_provider,
            vector_store=self._vector_store,
        )
        self._graph_tools = graph_tools
        self._history_compactor = HistoryCompactor()

    @staticmethod
    def _history_sort_key(doc: Any) -> tuple[str, str]:
        created_at = getattr(doc, "created_at", None)
        created_at_key = (
            created_at.isoformat() if (created_at is not None and hasattr(created_at, "isoformat")) else ""
        )
        return created_at_key, str(getattr(doc, "id", ""))

    async def _load_chat_history(
        self,
        session_id: uuid.UUID,
    ) -> list[dict[str, str]]:
        try:
            history_docs = await self._store.list_history_for_session(session_id)
        except Exception:
            return []

        ordered_docs = sorted(history_docs, key=self._history_sort_key)
        return [
            {
                "role": str(getattr(doc, "role", "")).replace("assistant", "model"),
                "content": str(getattr(doc, "content", "")),
            }
            for doc in ordered_docs
            if getattr(doc, "role", "") and getattr(doc, "content", "")
        ]

    async def _build_query_state(
        self,
        query: str,
        *,
        repo_path: str | None,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        repo_id: uuid.UUID | None,
        workflow_name: str | None,
        verification_payload: dict[str, Any] | None,
        max_attempts: int,
        allowed_repo_scopes: list[str] | None,
    ) -> GraphState:
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
        chat_history: list[dict[str, str]] = []
        history_message_count = 0
        if session_id:
            chat_history = await self._load_chat_history(session_id)
            chat_history = self._history_compactor.compact(
                chat_history,
                context_length=self._config.llm.context_length,
            )
            history_message_count = len(chat_history)
            await self._store.create_history(
                session_id=session_id,
                role="user",
                content=query,
            )

        is_builtin_prompt = bool(getattr(query_prompt, "is_builtin", False))
        return GraphState(
            query=query,
            session_id=session_id,
            user_id=user_id,
            repo_id=repo_id,
            repo_path=repo_path,
            workflow_context=workflow_context,
            chat_history=chat_history,
            metadata={
                "verification_payload": verification_payload,
                "max_attempts": max_attempts,
                "project_name": project_name,
                "query_prompt_name": getattr(query_prompt, "name", "query_reasoning"),
                "query_prompt_template": (
                    ""
                    if is_builtin_prompt
                    else getattr(query_prompt, "content_template", "")
                ),
                "query_prompt_defaults": dict(
                    getattr(query_prompt, "defaults", {}) or {}
                ),
                "query_prompt_source": "builtin" if is_builtin_prompt else "custom",
                "history_message_count": history_message_count,
            },
        )

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
        state = await self._build_query_state(
            query,
            repo_path=repo_path,
            session_id=session_id,
            user_id=user_id,
            repo_id=repo_id,
            workflow_name=workflow_name,
            verification_payload=verification_payload,
            max_attempts=max_attempts,
            allowed_repo_scopes=allowed_repo_scopes,
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
        return self._result_from_state(result)

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
        state = await self._build_query_state(
            query,
            repo_path=repo_path,
            session_id=session_id,
            user_id=user_id,
            repo_id=repo_id,
            workflow_name=workflow_name,
            verification_payload=verification_payload,
            max_attempts=max_attempts,
            allowed_repo_scopes=allowed_repo_scopes,
        )
        if self._config.graph.runtime == "langgraph":
            config = {"configurable": {"thread_id": str(session_id) if session_id else "default"}}
            async for event in self._graph.astream_events(state, config, version="v2"):
                event_name = event.get("event")
                name = event.get("name", "")
                
                if event_name == "on_chain_start" and name == "reasoning":
                    yield {"type": "attempt", "attempt": 1}
                
                elif event_name == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        yield {"type": "chunk", "attempt": 1, "delta": chunk.content}
                
                elif event_name == "on_chain_end" and name in {"merge_retrieved", "retriever"}:
                    output = event.get("data", {}).get("output", {})
                    docs = output.get("reranked_docs", []) or output.get("retrieved_docs", [])
                    if docs:
                        yield {"type": "sources", "sources": [{"path": d["path"], "score": d.get("score", 0.0)} for d in docs[:5]]}
                
                elif event_name == "on_chain_end" and name == "LangGraph":
                    final_data = event.get("data", {}).get("output", {})
                    if final_data:
                        final_state = GraphState.model_validate(final_data) if hasattr(GraphState, "model_validate") else GraphState(**final_data)
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
        else:
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
        approval_request = None
        if result.metadata.get("waiting_for_approval"):
            approval_request = list(result.metadata.get("interrupts", []) or [{}])[
                0
            ].get("value")
        cross_repo_graph_raw = result.workflow_context.get("cross_repo_graph")
        cross_repo_graph_summary: dict[str, int] | None = None
        if isinstance(cross_repo_graph_raw, dict):
            results = cross_repo_graph_raw.get("results") or []
            cross_repo_graph_summary = {
                "result_count": len(results),
                "scope_count": cross_repo_graph_raw.get("scope_count", 0),
            }
        return {
            "answer": result.llm_output.get("text", ""),
            "sources": result.reasoning_output.get("sources", []),
            "workflow_name": result.workflow_context.get("workflow_name"),
            "provider": result.llm_output.get("provider"),
            "model": result.llm_output.get("model"),
            "runtime": result.llm_output.get("runtime"),
            "orchestration_runtime": result.metadata.get("orchestration_runtime"),
            "edge": result.metadata.get("edge"),
            "guard_result": result.guard_result,
            "verification_result": result.verification_result,
            "transition_log": result.transition_log,
            "history_message_count": result.metadata.get("history_message_count"),
            "cross_repo_graph": cross_repo_graph_summary,
            "status": (
                "waiting_approval"
                if result.metadata.get("waiting_for_approval")
                else "completed"
            ),
            "approval_request": approval_request,
            "session_id": str(result.session_id) if result.session_id else None,
            "supervisor": {
                "used": bool(result.metadata.get("supervisor_used", False)),
                "selected_agent": result.metadata.get("supervisor_selected_agent"),
                "agents": list(result.metadata.get("supervisor_agents", []) or []),
            },
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

        project_name = Path(repo_path).name
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
        import os

        ignore_dirs = {
            ".git",
            ".svn",
            ".hg",
            "node_modules",
            "venv",
            ".venv",
            "__pycache__",
            ".minder_cache",
            ".gemini",
        }
        discovered: list[str] = []
        root_path = os.path.abspath(repo_path)
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [
                d for d in dirnames if d not in ignore_dirs and not d.startswith(".")
            ]
            for filename in filenames:
                if filename.startswith("."):
                    continue
                abs_path = os.path.join(dirpath, filename)
                discovered.append(os.path.relpath(abs_path, root_path))
        return discovered
