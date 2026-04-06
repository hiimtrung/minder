from __future__ import annotations

import math
import uuid
from typing import Any

from minder.store.document import DocumentStore
from minder.store.error import ErrorStore
from minder.store.interfaces import IVectorStore


class VectorStore(IVectorStore):
    def __init__(self, document_store: DocumentStore, error_store: ErrorStore) -> None:
        self._document_store = document_store
        self._error_store = error_store

    async def upsert_document(
        self,
        doc_id: uuid.UUID,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Not supported in Relational VectorStore."""
        pass

    async def delete_documents(self, doc_ids: list[uuid.UUID]) -> None:
        """Not supported in Relational VectorStore."""
        pass
    
    async def setup(self) -> None:
        """No setup needed for Relational VectorStore."""
        pass

    async def search_documents(
        self,
        query_embedding: list[float],
        *,
        project: str | None = None,
        doc_types: set[str] | None = None,
        limit: int = 5,
        score_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        docs = await self._document_store.list_documents(project=project)
        ranked: list[dict[str, Any]] = []
        for doc in docs:
            if doc_types is not None and doc.doc_type not in doc_types:
                continue
            embedding = doc.embedding if isinstance(doc.embedding, list) else None
            if not embedding:
                continue
            score = self._cosine_similarity(query_embedding, embedding)
            if score < score_threshold:
                continue
            ranked.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "path": doc.source_path,
                    "content": doc.content,
                    "score": round(score, 4),
                    "doc_type": doc.doc_type,
                }
            )
        ranked.sort(key=lambda item: float(item["score"]), reverse=True)
        return ranked[:limit]

    async def search_errors(
        self, query: str, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        return await self._error_store.search_errors(query, limit=limit)

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right, strict=False))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)
