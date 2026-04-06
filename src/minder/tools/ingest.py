from __future__ import annotations

from pathlib import Path

from minder.embedding.base import EmbeddingProvider
from minder.store.document import DocumentStore

SUPPORTED_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml", ".yml", ".yaml"}


class IngestTools:
    def __init__(
        self, 
        document_store: DocumentStore, 
        embedding_provider: EmbeddingProvider,
        vector_store: Any | None = None,
    ) -> None:
        self._document_store = document_store
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    async def minder_ingest_file(self, path: str, *, project: str | None = None) -> dict[str, object]:
        file_path = Path(path)
        content = file_path.read_text(encoding="utf-8")
        doc_type = self._doc_type_for_suffix(file_path.suffix)
        target_project = project or file_path.parent.name
        embedding = self._embedding_provider.embed(content)
        document = await self._document_store.upsert_document(
            title=file_path.name,
            content=content,
            doc_type=doc_type,
            source_path=str(file_path),
            project=target_project,
            chunks={"size": len(content)},
            embedding=embedding,
        )
        
        if self._vector_store and hasattr(self._vector_store, "upsert_document") and embedding:
            await self._vector_store.upsert_document(
                doc_id=document.id,
                embedding=embedding,
                payload={
                    "title": file_path.name,
                    "content": content,
                    "doc_type": doc_type,
                    "source_path": str(file_path),
                    "project": target_project,
                }
            )
            
        return {
            "document_id": document.id,
            "path": str(file_path),
            "project": target_project,
            "doc_type": doc_type,
        }

    async def minder_ingest_directory(
        self,
        path: str,
        *,
        project: str | None = None,
    ) -> dict[str, object]:
        root = Path(path)
        target_project = project or root.name
        ingested_paths: set[str] = set()
        ingested_count = 0

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if any(part.startswith(".") and part != ".minder" for part in file_path.parts):
                continue
            if file_path.suffix not in SUPPORTED_SUFFIXES:
                continue
            await self.minder_ingest_file(str(file_path), project=target_project)
            ingested_paths.add(str(file_path))
            ingested_count += 1

        # We first need to get the list of documents that WILL be deleted
        docs_to_delete = []
        if self._vector_store and hasattr(self._vector_store, "delete_documents"):
            existing = await self._document_store.list_documents(project=target_project)
            docs_to_delete = [
                doc.id for doc in existing 
                if doc.source_path not in ingested_paths
            ]

        await self._document_store.delete_documents_not_in_paths(
            project=target_project,
            keep_paths=ingested_paths,
        )
        
        if docs_to_delete and self._vector_store and hasattr(self._vector_store, "delete_documents"):
            await self._vector_store.delete_documents(docs_to_delete)
        return {
            "project": target_project,
            "ingested_count": ingested_count,
            "paths": sorted(ingested_paths),
        }

    @staticmethod
    def _doc_type_for_suffix(suffix: str) -> str:
        if suffix == ".py":
            return "code"
        if suffix in {".json", ".toml", ".yml", ".yaml"}:
            return "config"
        return "markdown"
