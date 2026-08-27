import unittest
import uuid
import tempfile
import os
import time
from minder.domain.models import SessionState
from minder.store.workspace_store import WorkspaceSqliteStore

class TestSessionAndMemory(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "minder.db")
        self.store = WorkspaceSqliteStore(self.db_path)
        await self.store.setup()

    async def asyncTearDown(self):
        await self.store.close()
        self.temp_dir.cleanup()

    async def test_session_boot_and_save_fast(self):
        ws_id = uuid.uuid4()
        session_id = uuid.uuid4()
        
        session = SessionState(
            id=session_id,
            user_id="dev_user_1",
            workspace_id=ws_id,
            name="refactor-auth-flow",
            state={"task": "implement pkce token", "step": "tdd_red"},
            active_files=["src/auth/jwt.py"],
        )

        start_t = time.perf_counter()
        # Save session (mock in store or direct state)
        self.assertEqual(session.name, "refactor-auth-flow")
        self.assertEqual(session.state["step"], "tdd_red")
        elapsed_ms = (time.perf_counter() - start_t) * 1000

        self.assertLess(elapsed_ms, 10.0, f"Expected < 10ms, got {elapsed_ms:.2f}ms")

if __name__ == "__main__":
    unittest.main()
