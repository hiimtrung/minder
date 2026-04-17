from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select, update

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

    async def get_document_by_path(
        self, source_path: str, *, project: str | None = None
    ) -> Document | None:
        async with self._store._session() as sess:
            stmt = select(Document).where(Document.source_path == source_path)
            if project is not None:
                stmt = stmt.where(Document.project == project)
            result = await sess.execute(stmt)
            return result.scalar_one_or_none()

    async def get_documents_by_ids(self, doc_ids: list[uuid.UUID]) -> list[Document]:
        if not doc_ids:
            return []
        async with self._store._session() as sess:
            stmt = select(Document).where(Document.id.in_(doc_ids))
            result = await sess.execute(stmt)
            return list(result.scalars().all())

    async def list_documents(self, project: str | None = None) -> list[Document]:
        async with self._store._session() as sess:
            stmt = select(Document)
            if project is not None:
                stmt = stmt.where(Document.project == project)
            result = await sess.execute(stmt)
            return list(result.scalars().all())

    async def upsert_document(
        self,
        *,
        title: str,
        content: str,
        doc_type: str,
        source_path: str,
        project: str,
        chunks: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> Document:
        existing = await self.get_document_by_path(source_path, project=project)
        if existing is None:
            return await self.create_document(
                title=title,
                content=content,
                doc_type=doc_type,
                source_path=source_path,
                project=project,
                chunks=chunks,
                embedding=embedding,
            )

        async with self._store._session() as sess:
            await sess.execute(
                update(Document)
                .where(Document.id == existing.id)
                .values(
                    title=title,
                    content=content,
                    doc_type=doc_type,
                    chunks=chunks or {},
                    embedding=embedding,
                    project=project,
                )
            )
            result = await sess.execute(select(Document).where(Document.id == existing.id))
            return result.scalar_one()

    async def delete_documents_not_in_paths(
        self, *, project: str, keep_paths: set[str]
    ) -> None:
        async with self._store._session() as sess:
            stmt = delete(Document).where(Document.project == project)
            if keep_paths:
                stmt = stmt.where(Document.source_path.not_in(keep_paths))
            await sess.execute(stmt)
