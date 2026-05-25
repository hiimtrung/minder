"""
Milvus Lite Vector Store — implements IVectorStore using embedded Milvus.

Milvus Lite is sync-only; all blocking calls are offloaded to a thread pool
via asyncio.to_thread() so the FastAPI event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from minder.store.interfaces import IDocumentRepository
from minder.store.milvus.client import MilvusClientWrapper

logger = logging.getLogger(__name__)

_COLLECTION = "vectors"
_MAX_TEXT_LEN = 1024


class MilvusVectorStore:
    """Vector store backed by Milvus Lite with COSINE ANN search."""

    def __init__(
        self,
        client: MilvusClientWrapper,
        document_store: IDocumentRepository,
        *,
        dimensions: int = 768,
    ) -> None:
        self._wrapper = client
        self._document_store = document_store
        self._dimensions = dimensions
        self._ready = False

    # -- Internal helpers --

    def _get_client(self):  # type: ignore[return]
        return self._wrapper.client

    def _setup_sync(self) -> None:
        from pymilvus import DataType  # type: ignore[import-untyped]

        c = self._get_client()
        if c.has_collection(_COLLECTION):
            info = c.describe_collection(_COLLECTION)
            for field in info.get("fields", []):
                if field.get("name") == "embedding":
                    existing_dim = field.get("params", {}).get("dim", 0)
                    if existing_dim and existing_dim != self._dimensions:
                        logger.warning(
                            "Milvus collection dimension mismatch: existing=%s expected=%s; recreating",
                            existing_dim,
                            self._dimensions,
                        )
                        c.drop_collection(_COLLECTION)
                        break  # fall through to recreate
                    return  # collection exists and is compatible
            else:
                return  # no embedding field found — treat as compatible

        schema = c.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, max_length=36, is_primary=True)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=self._dimensions)
        schema.add_field("title", DataType.VARCHAR, max_length=_MAX_TEXT_LEN)
        schema.add_field("source_path", DataType.VARCHAR, max_length=_MAX_TEXT_LEN)
        schema.add_field("doc_type", DataType.VARCHAR, max_length=128)
        schema.add_field("project", DataType.VARCHAR, max_length=256)

        index_params = c.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            metric_type="COSINE",
            index_type="FLAT",
        )

        c.create_collection(_COLLECTION, schema=schema, index_params=index_params)
        logger.info("Milvus Lite collection '%s' created (dim=%s)", _COLLECTION, self._dimensions)

    def _upsert_sync(
        self, doc_id: uuid.UUID, embedding: list[float], payload: dict[str, Any]
    ) -> None:
        c = self._get_client()
        c.upsert(
            _COLLECTION,
            data=[
                {
                    "id": str(doc_id),
                    "embedding": embedding,
                    "title": str(payload.get("title", ""))[:_MAX_TEXT_LEN],
                    "source_path": str(
                        payload.get("source_path", payload.get("path", ""))
                    )[:_MAX_TEXT_LEN],
                    "doc_type": str(payload.get("doc_type", ""))[:128],
                    "project": str(payload.get("project", ""))[:256],
                }
            ],
        )

    def _delete_sync(self, doc_ids: list[uuid.UUID]) -> None:
        c = self._get_client()
        c.delete(_COLLECTION, ids=[str(d) for d in doc_ids])

    def _search_sync(
        self,
        query_embedding: list[float],
        *,
        project: str | None,
        doc_types: set[str] | None,
        limit: int,
        score_threshold: float,
    ) -> list[dict[str, Any]]:
        c = self._get_client()

        filters: list[str] = []
        if project:
            safe = project.replace('"', '\\"')
            filters.append(f'project == "{safe}"')
        if doc_types:
            quoted = ", ".join(f'"{dt}"' for dt in sorted(doc_types))
            filters.append(f"doc_type in [{quoted}]")
        filter_expr = " and ".join(filters) if filters else ""

        results = c.search(
            _COLLECTION,
            data=[query_embedding],
            anns_field="embedding",
            limit=limit,
            filter=filter_expr or None,
            output_fields=["title", "source_path", "doc_type", "project"],
            search_params={"metric_type": "COSINE"},
        )

        hits: list[dict[str, Any]] = []
        for hit in results[0]:
            score = float(hit.get("distance", 0.0))
            if score < score_threshold:
                continue
            entity = hit.get("entity", {})
            hits.append(
                {
                    "id": hit["id"],
                    "score": round(score, 4),
                    "title": entity.get("title", ""),
                    "source_path": entity.get("source_path", ""),
                    "doc_type": entity.get("doc_type", ""),
                    "project": entity.get("project", ""),
                }
            )
        return hits

    # -- IVectorStore async interface --

    async def setup(self) -> None:
        if self._ready:
            return
        await asyncio.to_thread(self._setup_sync)
        self._ready = True

    async def upsert_document(
        self, doc_id: uuid.UUID, embedding: list[float], payload: dict[str, Any]
    ) -> None:
        if len(embedding) != self._dimensions:
            raise ValueError(
                f"Embedding length {len(embedding)} != configured {self._dimensions}"
            )
        await self.setup()
        await asyncio.to_thread(self._upsert_sync, doc_id, embedding, payload)

    async def delete_documents(self, doc_ids: list[uuid.UUID]) -> None:
        if not doc_ids:
            return
        await self.setup()
        await asyncio.to_thread(self._delete_sync, doc_ids)

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

        raw_hits = await asyncio.to_thread(
            self._search_sync,
            query_embedding,
            project=project,
            doc_types=doc_types,
            limit=limit,
            score_threshold=score_threshold,
        )

        doc_ids: list[uuid.UUID] = []
        for hit in raw_hits:
            try:
                doc_ids.append(uuid.UUID(str(hit["id"])))
            except ValueError:
                pass

        docs_by_id = {
            doc.id: doc
            for doc in await self._document_store.get_documents_by_ids(doc_ids)
        }

        ranked: list[dict[str, Any]] = []
        for hit in raw_hits:
            try:
                did = uuid.UUID(str(hit["id"]))
            except ValueError:
                did = None  # type: ignore[assignment]
            doc = docs_by_id.get(did) if did else None
            ranked.append(
                {
                    "id": did,
                    "title": getattr(doc, "title", None) or hit["title"],
                    "path": getattr(doc, "source_path", None) or hit["source_path"],
                    "content": getattr(doc, "content", None) or "",
                    "score": hit["score"],
                    "doc_type": getattr(doc, "doc_type", None) or hit["doc_type"],
                }
            )
        return ranked
