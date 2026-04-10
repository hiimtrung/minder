"""
Milvus Vector Store — implements IVectorStore using PyMilvus.

All operations execute in a thread pool since PyMilvus is synchronous.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from minder.store.interfaces import IDocumentRepository
from minder.store.milvus.client import MilvusClient
from minder.store.milvus.collections import get_document_schema


logger = logging.getLogger(__name__)


class MilvusVectorStore:
    def __init__(
        self,
        client: MilvusClient,
        document_store: IDocumentRepository,
        prefix: str = "minder_",
        dimensions: int = 768,
    ) -> None:
        self._client = client
        self._document_store = document_store
        self._prefix = prefix
        self._dimensions = dimensions
        self._doc_collection = f"{prefix}documents"
        self._collection_ready = False
        self._collection_lock = asyncio.Lock()

    async def setup(self) -> None:
        await self._ensure_collection_ready(force=True)

    async def _ensure_collection_ready(self, *, force: bool = False) -> None:
        if self._collection_ready and not force:
            return

        async with self._collection_lock:
            if self._collection_ready and not force:
                return

            loop = asyncio.get_running_loop()

            def _setup() -> None:
                if self._client.client.has_collection(self._doc_collection):
                    metadata = self._client.client.describe_collection(self._doc_collection)
                    current_dim = self._extract_embedding_dimension(metadata)
                    if current_dim is not None and current_dim != self._dimensions:
                        logger.warning(
                            "Milvus collection %s dimension mismatch: existing=%s expected=%s; recreating collection for reindex",
                            self._doc_collection,
                            current_dim,
                            self._dimensions,
                        )
                        self._client.client.drop_collection(self._doc_collection)

                if not self._client.client.has_collection(self._doc_collection):
                    self._create_collection()

            await loop.run_in_executor(None, _setup)
            self._collection_ready = True

    def _create_collection(self) -> None:
        schema = get_document_schema(self._dimensions)
        index_params = self._client.client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        self._client.client.create_collection(
            collection_name=self._doc_collection,
            schema=schema,
            index_params=index_params,
        )

    @staticmethod
    def _extract_embedding_dimension(metadata: Any) -> int | None:
        if not isinstance(metadata, dict):
            return None
        fields = metadata.get("fields", [])
        if not isinstance(fields, list):
            return None

        for field in fields:
            if not isinstance(field, dict):
                continue
            field_name = field.get("name") or field.get("field_name")
            if field_name != "embedding":
                continue

            for key in ("params", "type_params", "element_type_params"):
                params = field.get(key)
                if isinstance(params, dict) and params.get("dim") is not None:
                    return int(params["dim"])

            if field.get("dim") is not None:
                return int(field["dim"])

        return None

    def _validate_embedding_length(self, embedding: list[float]) -> None:
        if len(embedding) != self._dimensions:
            raise ValueError(
                f"Embedding length {len(embedding)} does not match configured Milvus dimension {self._dimensions}"
            )

    @staticmethod
    def _serialize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": str(payload.get("title", "")),
            "source_path": str(payload.get("source_path", payload.get("path", ""))),
            "doc_type": str(payload.get("doc_type", "")),
            "project": str(payload.get("project", "")),
        }

    async def upsert_document(
        self,
        doc_id: uuid.UUID,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None:
        self._validate_embedding_length(embedding)
        await self._ensure_collection_ready()
        loop = asyncio.get_running_loop()

        def _upsert() -> None:
            self._client.client.upsert(
                collection_name=self._doc_collection,
                data=[
                    {
                        "id": str(doc_id),
                        "embedding": embedding,
                        "project": payload.get("project", ""),
                        "doc_type": payload.get("doc_type", ""),
                        "payload": self._serialize_payload(payload),
                    }
                ],
            )

        await loop.run_in_executor(None, _upsert)

    async def delete_documents(self, doc_ids: list[uuid.UUID]) -> None:
        if not doc_ids:
            return
        loop = asyncio.get_running_loop()

        def _delete() -> None:
            id_list = [f"'{did}'" for did in doc_ids]
            expr = f"id in [{', '.join(id_list)}]"
            self._client.client.delete(
                collection_name=self._doc_collection,
                filter=expr,
            )

        await loop.run_in_executor(None, _delete)

    async def search_documents(
        self,
        query_embedding: list[float],
        *,
        project: str | None = None,
        doc_types: set[str] | None = None,
        limit: int = 5,
        score_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        self._validate_embedding_length(query_embedding)
        await self._ensure_collection_ready()
        loop = asyncio.get_running_loop()

        filter_expr = ""
        filters = []
        if project:
            filters.append(f'project == "{project}"')
        if doc_types:
            types_str = ", ".join(f'"{t}"' for t in doc_types)
            filters.append(f"doc_type in [{types_str}]")

        if filters:
            filter_expr = " and ".join(filters)

        def _search() -> Any:
            return self._client.client.search(
                collection_name=self._doc_collection,
                data=[query_embedding],
                filter=filter_expr,
                limit=limit,
                output_fields=["payload"],
            )

        results = await loop.run_in_executor(None, _search)

        hits_with_payload: list[tuple[Any, dict[str, Any]]] = []
        doc_ids: list[uuid.UUID] = []
        ranked: list[dict[str, Any]] = []
        if results and len(results) > 0:
            for hit in results[0]:
                if hit.distance < score_threshold:
                    continue
                payload = hit.entity.get("payload", {})
                doc_id = uuid.UUID(hit.id) if isinstance(hit.id, str) else hit.id
                if isinstance(doc_id, uuid.UUID):
                    doc_ids.append(doc_id)
                hits_with_payload.append((hit, payload if isinstance(payload, dict) else {}))

        docs_by_id = {
            doc.id: doc for doc in await self._document_store.get_documents_by_ids(doc_ids)
        }

        for hit, payload in hits_with_payload:
            doc_id = uuid.UUID(hit.id) if isinstance(hit.id, str) else hit.id
            doc = docs_by_id.get(doc_id) if isinstance(doc_id, uuid.UUID) else None
            ranked.append(
                {
                    "id": doc_id,
                    "title": getattr(doc, "title", None) or payload.get("title", ""),
                    "path": getattr(doc, "source_path", None)
                    or payload.get("source_path", payload.get("path", "")),
                    "content": getattr(doc, "content", None) or "",
                    "score": round(hit.distance, 4),
                    "doc_type": getattr(doc, "doc_type", None) or payload.get("doc_type", ""),
                }
            )

        return ranked
