"""
Milvus Vector Store — implements IVectorStore using PyMilvus.

All operations execute in a thread pool since PyMilvus is synchronous.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from minder.store.milvus.client import MilvusClient
from minder.store.milvus.collections import get_document_schema


class MilvusVectorStore:
    def __init__(self, client: MilvusClient, prefix: str = "minder_") -> None:
        self._client = client
        self._prefix = prefix
        self._doc_collection = f"{prefix}documents"

    async def setup(self) -> None:
        loop = asyncio.get_running_loop()

        def _setup() -> None:
            # Note: create_collection with index_params acts idempotently
            # in newer PyMilvus versions, or we can check has_collection
            if not self._client.client.has_collection(self._doc_collection):
                schema = get_document_schema()
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

        await loop.run_in_executor(None, _setup)

    async def upsert_document(
        self,
        doc_id: uuid.UUID,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None:
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
                        "payload": payload,
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

        ranked: list[dict[str, Any]] = []
        if results and len(results) > 0:
            for hit in results[0]:
                if hit.distance < score_threshold:
                    continue
                payload = hit.entity.get("payload", {})
                ranked.append(
                    {
                        "id": uuid.UUID(hit.id) if isinstance(hit.id, str) else hit.id,
                        "title": payload.get("title", ""),
                        "path": payload.get("path", payload.get("source_path", "")),
                        "content": payload.get("content", ""),
                        "score": round(hit.distance, 4),
                        "doc_type": payload.get("doc_type", ""),
                    }
                )

        return ranked
