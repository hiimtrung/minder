import unittest
import tempfile
import json
from pathlib import Path
from src.minder.presentation.cli.connect import generate_mcp_config, write_ide_configs

class TestCliConnect(unittest.TestCase):
    def test_generate_mcp_config(self):
        config = generate_mcp_config(
            hub_url="http://localhost:8800",
            client_key="mkc_test_123",
            workspace_name="fintech-platform",
        )
        self.assertIn("minder", config["mcpServers"])
        server_entry = config["mcpServers"]["minder"]
        self.assertEqual(server_entry["url"], "http://localhost:8800/sse")
        self.assertEqual(server_entry["headers"]["X-Minder-Client-Key"], "mkc_test_123")

    def test_write_ide_configs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir)
            files = write_ide_configs(
                project_dir=project_dir,
                hub_url="http://localhost:8800",
                client_key="mkc_test_123",
                workspace_name="fintech-platform",
            )
            self.assertGreaterEqual(len(files), 2)
            
            # Verify VS Code config
            vscode_mcp = project_dir / ".vscode" / "mcp.json"
            self.assertTrue(vscode_mcp.exists())
            with open(vscode_mcp) as f:
                data = json.load(f)
                self.assertIn("minder", data["mcpServers"])

            # Verify Cursor config
            cursor_mcp = project_dir / ".cursor" / "mcp.json"
            self.assertTrue(cursor_mcp.exists())

if __name__ == "__main__":
    unittest.main()
