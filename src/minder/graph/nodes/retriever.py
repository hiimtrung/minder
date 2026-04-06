from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import cast

from minder.embedding.base import EmbeddingProvider
from minder.graph.state import GraphState
from minder.store.interfaces import IVectorStore


class RetrieverNode:
    def __init__(
        self,
        top_k: int = 5,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: IVectorStore | None = None,
        score_threshold: float = 0.0,
    ) -> None:
        self._top_k = top_k
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._score_threshold = score_threshold

    async def run(self, state: GraphState) -> GraphState:
        project = state.metadata.get("project_name")
        if self._embedding_provider is not None and self._vector_store is not None:
            embedded = self._embedding_provider.embed(state.query)
            semantic_hits = await self._vector_store.search_documents(
                embedded,
                project=str(project) if isinstance(project, str) else None,
                limit=self._top_k,
                score_threshold=self._score_threshold,
            )
            if semantic_hits:
                state.retrieved_docs = semantic_hits
                state.reranked_docs = list(semantic_hits)
                state.metadata["retrieval_mode"] = "vector"
                return state

        repo_path = Path(state.repo_path or ".")
        query_terms = {term for term in state.query.lower().split() if len(term) > 2}
        candidates: list[dict[str, Any]] = []
        if repo_path.exists():
            for path in repo_path.rglob("*"):
                if not path.is_file():
                    continue
                if any(part.startswith(".") and part != ".minder" for part in path.parts):
                    continue
                if path.suffix not in {".py", ".md", ".txt", ".json"}:
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                lowered = content.lower()
                score = sum(lowered.count(term) for term in query_terms)
                if score == 0 and query_terms:
                    continue
                candidates.append(
                    {
                        "title": path.name,
                        "path": str(path),
                        "content": content,
                        "score": float(score),
                        "doc_type": "code" if path.suffix == ".py" else "markdown",
                    }
                )
        ranked = sorted(
            candidates,
            key=lambda item: cast(float, item["score"]),
            reverse=True,
        )
        state.retrieved_docs = ranked[: self._top_k]
        state.reranked_docs = list(state.retrieved_docs)
        state.metadata["retrieval_mode"] = "lexical"
        return state
