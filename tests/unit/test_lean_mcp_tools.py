import unittest
import uuid
import tempfile
import os
import time
from src.minder.domain.models import Workspace, Repository, Contract, CodeChunk
from src.minder.store.workspace_store import WorkspaceSqliteStore
from src.minder.tools.lean_query import LeanQueryTools

class MockVectorStore:
    def __init__(self):
        self.chunks = []

    def add_chunk(self, chunk: CodeChunk):
        self.chunks.append(chunk)

    async def search(self, query: str, workspace_id: uuid.UUID = None, limit: int = 5):
        # Deterministic instant search (< 5ms)
        results = []
        q = query.lower()
        for chunk in self.chunks:
            if workspace_id and chunk.workspace_id != workspace_id:
                continue
            if q in chunk.content.lower() or (chunk.symbol_name and q in chunk.symbol_name.lower()):
                results.append({
                    "path": chunk.file_path,
                    "symbol_name": chunk.symbol_name,
                    "language": chunk.language,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": chunk.content,
                    "score": 0.95,
                })
        return results[:limit]

class TestLeanMCPTools(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "minder.db")
        self.store = WorkspaceSqliteStore(self.db_path)
        await self.store.setup()

        self.vector_store = MockVectorStore()
        self.tools = LeanQueryTools(store=self.store, vector_store=self.vector_store)

        self.ws_id = uuid.uuid4()
        await self.store.create_workspace(Workspace(id=self.ws_id, name="FinTech", slug="fintech"))

        self.repo_id = uuid.uuid4()
        await self.store.create_repository(Repository(id=self.repo_id, workspace_id=self.ws_id, name="auth-service", repo_url="git@github.com:org/auth.git"))

    async def asyncTearDown(self):
        await self.store.close()
        self.temp_dir.cleanup()

    async def test_lean_search_code_returns_snippets_under_50ms(self):
        chunk = CodeChunk(
            id=uuid.uuid4(),
            workspace_id=self.ws_id,
            repo_id=self.repo_id,
            file_path="src/auth/jwt.py",
            symbol_name="verify_token",
            language="python",
            start_line=15,
            end_line=30,
            content="def verify_token(token: str) -> bool:\n    return len(token) > 10",
        )
        self.vector_store.add_chunk(chunk)

        start_t = time.perf_counter()
        results = await self.tools.minder_search_code(query="verify_token", workspace_id=self.ws_id)
        elapsed_ms = (time.perf_counter() - start_t) * 1000

        self.assertLess(elapsed_ms, 50.0, f"Expected < 50ms, got {elapsed_ms:.2f}ms")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["path"], "src/auth/jwt.py")
        self.assertEqual(results[0]["symbol_name"], "verify_token")
        self.assertEqual(results[0]["start_line"], 15)
        self.assertEqual(results[0]["end_line"], 30)
        self.assertIn("def verify_token", results[0]["content"])

    async def test_search_contracts_cross_repo(self):
        ctr = Contract(
            id=uuid.uuid4(),
            workspace_id=self.ws_id,
            repo_id=self.repo_id,
            kind="http_route",
            identifier="POST /api/v1/auth/login",
            raw_definition="router.post('/login', handler)",
            source_file="src/routes/auth.ts",
            start_line=10,
            end_line=25,
            language="typescript",
            metadata={"auth_required": False},
        )
        await self.store.save_contract(ctr)

        start_t = time.perf_counter()
        results = await self.tools.minder_search_contracts(query="login", workspace_id=self.ws_id)
        elapsed_ms = (time.perf_counter() - start_t) * 1000

        self.assertLess(elapsed_ms, 50.0)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["identifier"], "POST /api/v1/auth/login")
        self.assertEqual(results[0]["kind"], "http_route")
        self.assertEqual(results[0]["source_file"], "src/routes/auth.ts")

if __name__ == "__main__":
    unittest.main()
