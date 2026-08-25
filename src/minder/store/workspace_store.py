from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from minder.domain.models import Contract, Repository, Workspace


class WorkspaceSqliteStore:
    """High-performance SQLite WAL storage for Workspaces, Repositories, and Contracts."""

    def __init__(self, db_path: str) -> None:
        self._db_path = str(Path(db_path).expanduser())
        self._conn: sqlite3.Connection | None = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                timeout=10.0,
                autocommit=True,
            )
            self._conn.row_factory = sqlite3.Row
            # Enable WAL mode and performance pragmas
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA busy_timeout=5000;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
        return self._conn

    def _setup_tables(self) -> None:
        conn = self._get_connection()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS repositories (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                name TEXT NOT NULL,
                repo_url TEXT NOT NULL,
                default_branch TEXT NOT NULL DEFAULT 'main',
                local_path TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS contracts (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                repo_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                identifier TEXT NOT NULL,
                raw_definition TEXT NOT NULL,
                source_file TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                language TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
                FOREIGN KEY (repo_id) REFERENCES repositories(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_contracts_ws_kind ON contracts(workspace_id, kind);
            CREATE INDEX IF NOT EXISTS idx_contracts_identifier ON contracts(identifier);
            """
        )

    async def setup(self) -> None:
        await asyncio.to_thread(self._setup_tables)

    async def close(self) -> None:
        if self._conn is not None:
            await asyncio.to_thread(self._conn.close)
            self._conn = None

    # -- Workspace operations --

    def _create_workspace_sync(self, ws: Workspace) -> Workspace:
        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO workspaces (id, name, slug, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(ws.id),
                ws.name,
                ws.slug,
                ws.created_at.isoformat(),
                ws.updated_at.isoformat(),
            ),
        )
        return ws

    async def create_workspace(self, ws: Workspace) -> Workspace:
        return await asyncio.to_thread(self._create_workspace_sync, ws)

    def _get_workspace_sync(self, ws_id: uuid.UUID) -> Workspace | None:
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT id, name, slug, created_at, updated_at FROM workspaces WHERE id = ?",
            (str(ws_id),),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return Workspace(
            id=uuid.UUID(row["id"]),
            name=row["name"],
            slug=row["slug"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    async def get_workspace(self, ws_id: uuid.UUID) -> Workspace | None:
        return await asyncio.to_thread(self._get_workspace_sync, ws_id)

    def _list_workspaces_sync(self) -> list[Workspace]:
        conn = self._get_connection()
        cursor = conn.execute("SELECT id, name, slug, created_at, updated_at FROM workspaces ORDER BY name")
        return [
            Workspace(
                id=uuid.UUID(row["id"]),
                name=row["name"],
                slug=row["slug"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in cursor.fetchall()
        ]

    async def list_workspaces(self) -> list[Workspace]:
        return await asyncio.to_thread(self._list_workspaces_sync)

    # -- Repository operations --

    def _create_repository_sync(self, repo: Repository) -> Repository:
        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO repositories (id, workspace_id, name, repo_url, default_branch, local_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(repo.id),
                str(repo.workspace_id),
                repo.name,
                repo.repo_url,
                repo.default_branch,
                repo.local_path,
                repo.created_at.isoformat(),
            ),
        )
        return repo

    async def create_repository(self, repo: Repository) -> Repository:
        return await asyncio.to_thread(self._create_repository_sync, repo)

    def _list_repositories_by_workspace_sync(self, workspace_id: uuid.UUID) -> list[Repository]:
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT id, workspace_id, name, repo_url, default_branch, local_path, created_at
            FROM repositories WHERE workspace_id = ? ORDER BY name
            """,
            (str(workspace_id),),
        )
        return [
            Repository(
                id=uuid.UUID(row["id"]),
                workspace_id=uuid.UUID(row["workspace_id"]),
                name=row["name"],
                repo_url=row["repo_url"],
                default_branch=row["default_branch"],
                local_path=row["local_path"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in cursor.fetchall()
        ]

    async def list_repositories_by_workspace(self, workspace_id: uuid.UUID) -> list[Repository]:
        return await asyncio.to_thread(self._list_repositories_by_workspace_sync, workspace_id)

    # -- Contract operations --

    def _save_contract_sync(self, contract: Contract) -> Contract:
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO contracts (
                id, workspace_id, repo_id, kind, identifier, raw_definition,
                source_file, start_line, end_line, language, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(contract.id),
                str(contract.workspace_id),
                str(contract.repo_id),
                contract.kind,
                contract.identifier,
                contract.raw_definition,
                contract.source_file,
                contract.start_line,
                contract.end_line,
                contract.language,
                json.dumps(contract.metadata, ensure_ascii=False),
                contract.created_at.isoformat(),
            ),
        )
        return contract

    async def save_contract(self, contract: Contract) -> Contract:
        return await asyncio.to_thread(self._save_contract_sync, contract)

    def _search_contracts_sync(
        self,
        workspace_id: uuid.UUID,
        query: str,
        kind: str | None = None,
        limit: int = 10,
    ) -> list[Contract]:
        conn = self._get_connection()
        query_pattern = f"%{query}%"
        if kind:
            cursor = conn.execute(
                """
                SELECT id, workspace_id, repo_id, kind, identifier, raw_definition,
                       source_file, start_line, end_line, language, metadata_json, created_at
                FROM contracts
                WHERE workspace_id = ? AND kind = ? AND (identifier LIKE ? OR raw_definition LIKE ?)
                ORDER BY length(identifier) ASC
                LIMIT ?
                """,
                (str(workspace_id), kind, query_pattern, query_pattern, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, workspace_id, repo_id, kind, identifier, raw_definition,
                       source_file, start_line, end_line, language, metadata_json, created_at
                FROM contracts
                WHERE workspace_id = ? AND (identifier LIKE ? OR raw_definition LIKE ?)
                ORDER BY length(identifier) ASC
                LIMIT ?
                """,
                (str(workspace_id), query_pattern, query_pattern, limit),
            )

        return [
            Contract(
                id=uuid.UUID(row["id"]),
                workspace_id=uuid.UUID(row["workspace_id"]),
                repo_id=uuid.UUID(row["repo_id"]),
                kind=row["kind"],
                identifier=row["identifier"],
                raw_definition=row["raw_definition"],
                source_file=row["source_file"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                language=row["language"],
                metadata=json.loads(row["metadata_json"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in cursor.fetchall()
        ]

    async def search_contracts(
        self,
        workspace_id: uuid.UUID,
        query: str,
        kind: str | None = None,
        limit: int = 10,
    ) -> list[Contract]:
        return await asyncio.to_thread(
            self._search_contracts_sync, workspace_id, query, kind, limit
        )
