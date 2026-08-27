import unittest
import uuid
from datetime import datetime
from minder.domain.models import (
    Workspace,
    Repository,
    Contract,
    CodeChunk,
)

class TestDomainModels(unittest.TestCase):
    def test_workspace_creation(self):
        ws_id = uuid.uuid4()
        ws = Workspace(
            id=ws_id,
            name="FinTech Platform",
            slug="fintech-platform",
        )
        self.assertEqual(ws.id, ws_id)
        self.assertEqual(ws.name, "FinTech Platform")
        self.assertEqual(ws.slug, "fintech-platform")
        self.assertIsInstance(ws.created_at, datetime)

    def test_repository_creation(self):
        ws_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        repo = Repository(
            id=repo_id,
            workspace_id=ws_id,
            name="backend-api",
            repo_url="git@github.com:org/backend-api.git",
            default_branch="main",
            local_path="/projects/backend-api",
        )
        self.assertEqual(repo.id, repo_id)
        self.assertEqual(repo.workspace_id, ws_id)
        self.assertEqual(repo.name, "backend-api")
        self.assertEqual(repo.default_branch, "main")

    def test_contract_creation(self):
        ws_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        ctr_id = uuid.uuid4()
        contract = Contract(
            id=ctr_id,
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
        self.assertEqual(contract.id, ctr_id)
        self.assertEqual(contract.kind, "http_route")
        self.assertEqual(contract.identifier, "POST /api/v1/auth/login")
        self.assertEqual(contract.language, "typescript")

    def test_code_chunk_creation(self):
        ws_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        chunk = CodeChunk(
            id=chunk_id,
            workspace_id=ws_id,
            repo_id=repo_id,
            file_path="src/auth/jwt.py",
            symbol_name="verify_token",
            language="python",
            start_line=15,
            end_line=45,
            content="def verify_token(token: str):\n    return decode(token)",
            imports_context="import jwt",
        )
        self.assertEqual(chunk.id, chunk_id)
        self.assertEqual(chunk.symbol_name, "verify_token")
        self.assertEqual(chunk.start_line, 15)
        self.assertEqual(chunk.end_line, 45)

if __name__ == "__main__":
    unittest.main()
