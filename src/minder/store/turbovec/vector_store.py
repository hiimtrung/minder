"""
Turbovec Vector Store — implements IVectorStore using Turbovec (high-performance vector quantization index).

Runs search and index write operations on a background thread pool via asyncio.to_thread()
so the main thread's FastAPI event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from minder.store.interfaces import IDocumentRepository

logger = logging.getLogger(__name__)


class TurbovecVectorStore:
    """Vector store backed by Turbovec IdMapIndex."""

    def __init__(
        self,
        db_path: str,
        document_store: IDocumentRepository,
        *,
        dimensions: int = 768,
    ) -> None:
        self._db_path = db_path
        self._document_store = document_store
        self._dimensions = dimensions
        self._index: Any = None
        self._id_map: dict[int, uuid.UUID] = {}  # uint64_id -> original doc_uuid
        self._ready = False

    # -- Internal helpers (run synchronously in thread offloads) --

    def _setup_sync(self) -> None:
        import os
        import json
        from pathlib import Path
        from turbovec import IdMapIndex  # type: ignore[import-untyped]

        db_path = Path(self._db_path).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path_expanded = str(db_path)
        meta_path = self._db_path_expanded + ".meta"

        if os.path.exists(self._db_path_expanded) and os.path.exists(meta_path):
            try:
                self._index = IdMapIndex.load(self._db_path_expanded)
                with open(meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._id_map = {int(k): uuid.UUID(v) for k, v in data.items()}
                
                # Check for dimension compatibility
                if self._index.dim != self._dimensions:
                    logger.warning(
                        "Turbovec index dimension mismatch: existing=%s expected=%s; recreating",
                        self._index.dim,
                        self._dimensions,
                    )
                    # Recreate if mismatch
                    self._index = IdMapIndex(dim=self._dimensions, bit_width=4)
                    self._id_map = {}
                else:
                    logger.info(
                        "Turbovec index loaded from %s (size=%s, dim=%s)",
                        self._db_path_expanded,
                        len(self._id_map),
                        self._dimensions,
                    )
                return
            except Exception as e:
                logger.warning("Failed to load Turbovec index, recreating: %s", e)

        # Create fresh index
        self._index = IdMapIndex(dim=self._dimensions, bit_width=4)
        self._id_map = {}
        logger.info("Created fresh Turbovec index (dim=%s)", self._dimensions)

    def _save_sync(self) -> None:
        import json
        if self._index is None:
            return
        
        try:
            # Write Turbovec binary index
            self._index.write(self._db_path_expanded)
            # Write companion metadata ID mapping
            meta_path = self._db_path_expanded + ".meta"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({str(k): str(v) for k, v in self._id_map.items()}, f)
        except Exception as e:
            logger.error("Failed to write Turbovec database/mapping: %s", e)

    def _upsert_sync(
        self, doc_id: uuid.UUID, embedding: list[float], payload: dict[str, Any]
    ) -> None:
        import numpy as np

        # Stably map 128-bit UUID to 64-bit unsigned integer
        uint64_id = doc_id.int & 0xFFFFFFFFFFFFFFFF

        # IdMapIndex requires removing first to avoid duplicate slots for the same ID
        if uint64_id in self._id_map:
            try:
                self._index.remove(uint64_id)
            except Exception:
                pass

        vec = np.array([embedding], dtype=np.float32)
        ids = np.array([uint64_id], dtype=np.uint64)
        self._index.add_with_ids(vec, ids)

        self._id_map[uint64_id] = doc_id
        self._save_sync()

    def _delete_sync(self, doc_ids: list[uuid.UUID]) -> None:
        if not doc_ids or self._index is None:
            return

        for d in doc_ids:
            uint64_id = d.int & 0xFFFFFFFFFFFFFFFF
            try:
                self._index.remove(uint64_id)
            except Exception:
                pass
            self._id_map.pop(uint64_id, None)

        self._save_sync()

    def _search_sync(
        self,
        query_embedding: list[float],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        import numpy as np

        if self._index is None or len(self._id_map) == 0:
            return []

        query = np.array([query_embedding], dtype=np.float32)
        
        # Search a wider pool to allow metadata filtering downstream
        k = max(limit * 5, 100)
        scores, indices = self._index.search(query, k=k)

        if len(scores) == 0 or len(scores[0]) == 0:
            return []

        hits: list[dict[str, Any]] = []
        for score, uint64_id in zip(scores[0], indices[0], strict=False):
            doc_id = self._id_map.get(int(uint64_id))
            if doc_id:
                hits.append({
                    "id": doc_id,
                    "score": float(score),
                })
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
            limit=limit,
        )

        if not raw_hits:
            return []

        doc_ids = [hit["id"] for hit in raw_hits]
        docs_by_id = {
            doc.id: doc
            for doc in await self._document_store.get_documents_by_ids(doc_ids)
        }

        ranked: list[dict[str, Any]] = []
        for hit in raw_hits:
            doc_id = hit["id"]
            doc = docs_by_id.get(doc_id)
            if not doc:
                continue

            if project and doc.project != project:
                continue

            if doc_types and doc.doc_type not in doc_types:
                continue

            score = hit["score"]
            if score < score_threshold:
                continue

            ranked.append(
                {
                    "id": doc_id,
                    "title": getattr(doc, "title", None) or "",
                    "path": getattr(doc, "source_path", None) or "",
                    "content": getattr(doc, "content", None) or "",
                    "score": round(score, 4),
                    "doc_type": getattr(doc, "doc_type", None) or "",
                }
            )

            if len(ranked) >= limit:
                break

        return ranked
