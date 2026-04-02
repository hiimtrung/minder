from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from minder.models.document import Document
from minder.store.relational import RelationalStore


class DocumentStore:
    def __init__(self, store: RelationalStore) -> None:
        self._store = store

    async def create_document(
        self,
        title: str,
        content: str,
        doc_type: str,
        source_path: str,
        project: str,
        *,
        chunks: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> Document:
        async with self._store._session() as sess:
            document = Document(
                id=uuid.uuid4(),
                title=title,
                content=content,
                doc_type=doc_type,
                source_path=source_path,
                chunks=chunks or {},
                embedding=embedding,
                project=project,
            )
            sess.add(document)
            await sess.flush()
            await sess.refresh(document)
            return document

    async def list_documents(self, project: str | None = None) -> list[Document]:
        async with self._store._session() as sess:
            stmt = select(Document)
            if project is not None:
                stmt = stmt.where(Document.project == project)
            result = await sess.execute(stmt)
            return list(result.scalars().all())
