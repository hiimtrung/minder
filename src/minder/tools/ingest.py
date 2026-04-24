from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from minder.chunking.splitter import TextSplitter
from minder.embedding.base import EmbeddingProvider
from minder.store.interfaces import IDocumentRepository

SUPPORTED_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml", ".yml", ".yaml"}

# Maximum raw bytes to read from a URL response (4 MB).
_MAX_URL_BYTES = 4 * 1024 * 1024


class IngestTools:
    def __init__(
        self, 
        document_store: IDocumentRepository, 
        embedding_provider: EmbeddingProvider,
        vector_store: Any | None = None,
    ) -> None:
        self._document_store = document_store
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    async def minder_ingest_file(self, path: str, *, project: str | None = None) -> dict[str, object]:
        file_path = Path(path)
        doc_type = self._doc_type_for_suffix(file_path.suffix)
        target_project = project or file_path.parent.name
        file_stat = file_path.stat()
        existing = await self._document_store.get_document_by_path(
            str(file_path),
            project=target_project,
        )
        vector_enabled = bool(self._vector_store and hasattr(self._vector_store, "upsert_document"))

        if existing is not None and self._is_current_file_document(
            existing,
            title=file_path.name,
            doc_type=doc_type,
            project=target_project,
            file_size=file_stat.st_size,
            mtime_ns=file_stat.st_mtime_ns,
            vector_enabled=vector_enabled,
        ):
            return {
                "document_id": existing.id,
                "path": str(file_path),
                "project": target_project,
                "doc_type": doc_type,
            }

        content = file_path.read_text(encoding="utf-8")
        embedding = self._embedding_provider.embed(content)
        chunks = {
            "size": len(content),
            "file_size": file_stat.st_size,
            "mtime_ns": file_stat.st_mtime_ns,
            "vector_indexed": not vector_enabled,
        }
        document = await self._document_store.upsert_document(
            title=file_path.name,
            content=content,
            doc_type=doc_type,
            source_path=str(file_path),
            project=target_project,
            chunks=chunks,
            embedding=embedding,
        )
        
        if self._vector_store and vector_enabled and embedding:
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
            chunks["vector_indexed"] = True
            document = await self._document_store.upsert_document(
                title=file_path.name,
                content=content,
                doc_type=doc_type,
                source_path=str(file_path),
                project=target_project,
                chunks=chunks,
                embedding=embedding,
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

        import os
        ignore_dirs = {".git", ".svn", ".hg", "node_modules", "venv", ".venv", "__pycache__", ".minder_cache", ".gemini"}
        
        for dirpath, dirnames, filenames in os.walk(path):
            # Prune ignored directories
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]
            
            for filename in filenames:
                if filename.startswith("."):
                    continue
                file_path = Path(dirpath) / filename
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

    # ------------------------------------------------------------------
    # URL ingestion
    # ------------------------------------------------------------------

    async def minder_ingest_url(
        self,
        url: str,
        *,
        project: str | None = None,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> dict[str, object]:
        """Fetch *url* via HTTP, chunk the text, embed, and upsert each chunk.

        Content-type detection:
        - ``text/html``: strip tags naively (extract visible text via a
          whitespace-collapse pass — no external HTML parser required).
        - ``text/markdown`` / ``text/plain`` / unknown text: use as-is.

        Returns a summary dict with ``url``, ``project``, ``chunk_count``,
        and ``doc_ids`` (list of upserted document IDs).
        """
        parsed = urlparse(url)
        target_project = project or (parsed.netloc.replace(".", "_") or "url_ingest")

        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            response = await client.get(url)
            response.raise_for_status()

        raw = response.content[:_MAX_URL_BYTES]
        content_type = response.headers.get("content-type", "").lower()

        if "text/html" in content_type:
            text = self._strip_html(raw.decode("utf-8", errors="replace"))
            doc_type = "markdown"
        else:
            text = raw.decode("utf-8", errors="replace")
            doc_type = "markdown"

        splitter = TextSplitter(chunk_size=chunk_size, overlap=overlap)
        chunks = splitter.split(text)

        doc_ids: list[str] = []
        for i, chunk in enumerate(chunks):
            embedding = self._embedding_provider.embed(chunk.content)
            title = f"{parsed.path.rstrip('/').rsplit('/', 1)[-1] or parsed.netloc}_chunk{i}"
            document = await self._document_store.upsert_document(
                title=title,
                content=chunk.content,
                doc_type=doc_type,
                source_path=url,
                project=target_project,
                chunks={"chunk_index": i, "start_char": chunk.start_char, "end_char": chunk.end_char},
                embedding=embedding,
            )
            if self._vector_store and hasattr(self._vector_store, "upsert_document") and embedding:
                await self._vector_store.upsert_document(
                    doc_id=document.id,
                    embedding=embedding,
                    payload={
                        "title": title,
                        "content": chunk.content,
                        "doc_type": doc_type,
                        "source_path": url,
                        "project": target_project,
                    },
                )
            doc_ids.append(str(document.id))

        return {
            "url": url,
            "project": target_project,
            "chunk_count": len(chunks),
            "doc_ids": doc_ids,
        }

    # ------------------------------------------------------------------
    # Git ingestion
    # ------------------------------------------------------------------

    async def minder_ingest_git(
        self,
        repo_url: str,
        *,
        project: str | None = None,
        branch: str | None = None,
    ) -> dict[str, object]:
        """Shallow-clone *repo_url*, ingest its contents, then clean up.

        The clone is written to a temp directory that is always removed on exit
        (success or failure).  Internally delegates to
        :meth:`minder_ingest_directory` so the same chunk→embed→store pipeline
        applies.

        Args:
            repo_url: HTTPS or SSH git URL.
            project:  Project label forwarded to document store. Defaults to
                      the repo name derived from the URL.
            branch:   Optional branch / tag to clone (``--branch``). When
                      ``None`` the remote's default branch is used.

        Returns a dict with ``repo_url``, ``project``, ``ingested_count``,
        and ``paths``.
        """
        # Derive a sensible project name from the URL path.
        repo_name = urlparse(repo_url).path.rstrip("/").rsplit("/", 1)[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        target_project = project or repo_name or "git_ingest"

        tmp_dir = tempfile.mkdtemp(prefix="minder_git_")
        try:
            cmd = ["git", "clone", "--depth=1", "--single-branch"]
            if branch:
                cmd += ["--branch", branch]
            cmd += [repo_url, tmp_dir]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"git clone failed (exit {result.returncode}): {result.stderr.strip()}"
                )

            ingest_result = await self.minder_ingest_directory(
                tmp_dir,
                project=target_project,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return {
            "repo_url": repo_url,
            **ingest_result,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_html(html: str) -> str:
        """Very lightweight HTML → plain-text converter (no deps).

        Removes ``<script>``/``<style>`` blocks, strips all remaining tags,
        and collapses runs of whitespace.
        """
        import re

        # Drop script / style blocks entirely.
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        # Replace block-level elements with newlines for readability.
        html = re.sub(r"</(p|div|li|h[1-6]|br)>", "\n", html, flags=re.IGNORECASE)
        # Strip remaining tags.
        html = re.sub(r"<[^>]+>", " ", html)
        # Decode common HTML entities.
        for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
            html = html.replace(entity, char)
        # Collapse whitespace.
        html = re.sub(r"[ \t]+", " ", html)
        html = re.sub(r"\n{3,}", "\n\n", html)
        return html.strip()

    @staticmethod
    def _doc_type_for_suffix(suffix: str) -> str:
        if suffix == ".py":
            return "code"
        if suffix in {".json", ".toml", ".yml", ".yaml"}:
            return "config"
        return "markdown"

    @staticmethod
    def _is_current_file_document(
        document: Any,
        *,
        title: str,
        doc_type: str,
        project: str,
        file_size: int,
        mtime_ns: int,
        vector_enabled: bool,
    ) -> bool:
        chunks = getattr(document, "chunks", {})
        if not isinstance(chunks, dict):
            return False
        if getattr(document, "title", None) != title:
            return False
        if getattr(document, "doc_type", None) != doc_type:
            return False
        if getattr(document, "project", None) != project:
            return False
        if chunks.get("file_size") != file_size:
            return False
        if chunks.get("mtime_ns") != mtime_ns:
            return False
        if vector_enabled and chunks.get("vector_indexed") is not True:
            return False
        return True
