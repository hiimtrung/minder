import unittest
import uuid
import tempfile
import os
from pathlib import Path
from src.minder.domain.models import Workspace, Repository, Contract
from src.minder.store.workspace_store import WorkspaceSqliteStore

class TestWorkspaceSqliteStore(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_minder.db")
        self.store = WorkspaceSqliteStore(self.db_path)
        await self.store.setup()

    async def asyncTearDown(self):
        await self.store.close()
        self.temp_dir.cleanup()

    async def test_workspace_crud(self):
        ws_id = uuid.uuid4()
        ws = Workspace(id=ws_id, name="FinTech Core", slug="fintech-core")
        
        # Create
        created = await self.store.create_workspace(ws)
        self.assertEqual(created.name, "FinTech Core")

        # Get
        retrieved = await self.store.get_workspace(ws_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.slug, "fintech-core")

        # List
        all_ws = await self.store.list_workspaces()
        self.assertEqual(len(all_ws), 1)
        self.assertEqual(all_ws[0].id, ws_id)

    async def test_repository_crud(self):
        ws_id = uuid.uuid4()
        await self.store.create_workspace(Workspace(id=ws_id, name="FinTech", slug="fintech"))

        repo_id = uuid.uuid4()
        repo = Repository(
            id=repo_id,
            workspace_id=ws_id,
            name="backend-api",
            repo_url="git@github.com:org/backend-api.git",
            default_branch="main",
        )
        await self.store.create_repository(repo)

        repos = await self.store.list_repositories_by_workspace(ws_id)
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0].name, "backend-api")

    async def test_contract_crud_and_search(self):
        ws_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        await self.store.create_workspace(Workspace(id=ws_id, name="FinTech", slug="fintech"))
        await self.store.create_repository(Repository(id=repo_id, workspace_id=ws_id, name="auth-service", repo_url="git@github.com:org/auth.git"))

        ctr1 = Contract(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            repo_id=repo_id,
            kind="http_route",
            identifier="POST /api/v1/auth/login",
            raw_definition="router.post('/login', handler)",
            source_file="src/routes/auth.ts",
            start_line=10,
            end_line=25,
            language="typescript",
            metadata={"auth_required": False},
        )
        ctr2 = Contract(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            repo_id=repo_id,
            kind="dto_schema",
            identifier="LoginRequestDTO",
            raw_definition="interface LoginRequestDTO { email: string; }",
            source_file="src/dto/auth.ts",
            start_line=1,
            end_line=5,
            language="typescript",
        )

        await self.store.save_contract(ctr1)
        await self.store.save_contract(ctr2)

        # Search by identifier query
        results = await self.store.search_contracts(workspace_id=ws_id, query="login")
        self.assertEqual(len(results), 2)

        # Filter by kind
        dto_results = await self.store.search_contracts(workspace_id=ws_id, query="login", kind="dto_schema")
        self.assertEqual(len(dto_results), 1)
        self.assertEqual(dto_results[0].identifier, "LoginRequestDTO")

if __name__ == "__main__":
    unittest.main()
