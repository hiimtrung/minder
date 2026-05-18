"""Qdrant Vector Store — implements IVectorStore using native Qdrant vector search."""

from __future__ import annotations
import logging
import uuid
from typing import Any
from qdrant_client import models
from minder.store.qdrant.client import QdrantClientWrapper
from minder.store.interfaces import IDocumentRepository

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    """Vector store backed by Qdrant with native cosine similarity search."""

    def __init__(
        self,
        client: QdrantClientWrapper,
        document_store: IDocumentRepository,
        *,
        prefix: str = "minder_",
        dimensions: int = 768,
    ) -> None:
        self._client = client
        self._c = client.client
        self._document_store = document_store
        self._collection = f"{prefix}vectors"
        self._dimensions = dimensions
        self._ready = False

    async def setup(self) -> None:
        if self._ready:
            return
        exists = await self._c.collection_exists(self._collection)
        if exists:
            info = await self._c.get_collection(self._collection)
            current_dim = info.config.params.vectors
            if (
                isinstance(current_dim, models.VectorParams)
                and current_dim.size != self._dimensions
            ):
                logger.warning(
                    "Qdrant collection %s dimension mismatch: existing=%s expected=%s; recreating",
                    self._collection,
                    current_dim.size,
                    self._dimensions,
                )
                await self._c.delete_collection(self._collection)
                exists = False
        if not exists:
            await self._c.create_collection(
                self._collection,
                vectors_config=models.VectorParams(
                    size=self._dimensions, distance=models.Distance.COSINE
                ),
            )
        self._ready = True

    async def upsert_document(
        self, doc_id: uuid.UUID, embedding: list[float], payload: dict[str, Any]
    ) -> None:
        if len(embedding) != self._dimensions:
            raise ValueError(
                f"Embedding length {len(embedding)} != configured {self._dimensions}"
            )
        await self.setup()
        await self._c.upsert(
            self._collection,
            points=[
                models.PointStruct(
                    id=str(doc_id),
                    vector=embedding,
                    payload={
                        "title": str(payload.get("title", "")),
                        "source_path": str(
                            payload.get("source_path", payload.get("path", ""))
                        ),
                        "doc_type": str(payload.get("doc_type", "")),
                        "project": str(payload.get("project", "")),
                    },
                )
            ],
        )

    async def delete_documents(self, doc_ids: list[uuid.UUID]) -> None:
        if not doc_ids:
            return
        await self.setup()
        await self._c.delete(
            self._collection,
            points_selector=models.PointIdsList(points=[str(d) for d in doc_ids]),
        )

    async def search_documents(
        self,
        query_embedding: list[float],
        *,
        project: str | None = None,
        doc_types: set[str] | None = None,
        limit: int = 5,
        score_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        if len(query_embedding) != self._dimensions:
            raise ValueError(
                f"Embedding length {len(query_embedding)} != configured {self._dimensions}"
            )
        await self.setup()
        must: list[Any] = []
        if project:
            must.append(
                models.FieldCondition(
                    key="project", match=models.MatchValue(value=project)
                )
            )
        if doc_types:
            must.append(
                models.FieldCondition(
                    key="doc_type", match=models.MatchAny(any=list(doc_types))
                )
            )
        filt = models.Filter(must=must) if must else None

        results = await self._c.query_points(
            self._collection,
            query=query_embedding,
            query_filter=filt,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )

        doc_ids: list[uuid.UUID] = []
        hits: list[tuple[Any, dict[str, Any]]] = []
        for point in results.points:
            payload = dict(point.payload or {})
            try:
                did: Any = uuid.UUID(str(point.id))
                doc_ids.append(did)
            except ValueError:
                did = point.id
            hits.append((point, payload))

        docs_by_id = {
            doc.id: doc
            for doc in await self._document_store.get_documents_by_ids(doc_ids)
        }
        ranked: list[dict[str, Any]] = []
        for point, payload in hits:
            try:
                doc_did: Any = uuid.UUID(str(point.id))
            except ValueError:
                doc_did = point.id
            doc = docs_by_id.get(doc_did) if isinstance(doc_did, uuid.UUID) else None
            ranked.append(
                {
                    "id": doc_did,
                    "title": getattr(doc, "title", None) or payload.get("title", ""),
                    "path": getattr(doc, "source_path", None)
                    or payload.get("source_path", ""),
                    "content": getattr(doc, "content", None) or "",
                    "score": round(point.score, 4),
                    "doc_type": getattr(doc, "doc_type", None)
                    or payload.get("doc_type", ""),
                }
            )
        return ranked
