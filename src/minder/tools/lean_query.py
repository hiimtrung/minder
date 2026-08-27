from __future__ import annotations

import uuid
from typing import Any
from minder.store.workspace_store import WorkspaceSqliteStore


class LeanQueryTools:
    """Lean, fast, deterministic retrieval tools without nested LLM inference loops (< 50ms)."""

    def __init__(self, store: WorkspaceSqliteStore, vector_store: Any = None) -> None:
        self._store = store
        self._vector_store = vector_store

    async def minder_search_code(
        self,
        query: str,
        *,
        workspace_id: uuid.UUID | None = None,
        repo_id: uuid.UUID | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search code chunks returning full snippet content, symbol names, and line numbers."""
        if self._vector_store is None:
            return []

        if hasattr(self._vector_store, "search"):
            return await self._vector_store.search(
                query=query,
                workspace_id=workspace_id,
                limit=limit,
            )

        if hasattr(self._vector_store, "search_documents"):
            hits = await self._vector_store.search_documents(
                query_embedding=[],
                limit=limit,
            )
            return [
                {
                    "path": hit.get("path", ""),
                    "symbol_name": hit.get("symbol_name"),
                    "language": hit.get("language", ""),
                    "start_line": hit.get("start_line", 1),
                    "end_line": hit.get("end_line", 1),
                    "content": hit.get("content", ""),
                    "score": hit.get("score", 0.0),
                }
                for hit in hits
            ]

        return []

    async def minder_search_contracts(
        self,
        query: str,
        *,
        workspace_id: uuid.UUID,
        kind: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search cross-repo contracts (Routes, DTOs, gRPC methods, schemas) to prevent LLM hallucinations."""
        contracts = await self._store.search_contracts(
            workspace_id=workspace_id,
            query=query,
            kind=kind,
            limit=limit,
        )
        return [
            {
                "id": str(c.id),
                "identifier": c.identifier,
                "kind": c.kind,
                "source_file": c.source_file,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "language": c.language,
                "raw_definition": c.raw_definition,
                "metadata": c.metadata,
            }
            for c in contracts
        ]
