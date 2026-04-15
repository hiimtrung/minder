from __future__ import annotations

import json
from pathlib import Path

import minder.cli as cli
from minder.cli import main


def test_login_persists_client_config(tmp_path, capsys) -> None:  # noqa: ANN001
    config_path = tmp_path / "client.json"

    exit_code = main(
        [
            "login",
            "--client-key",
            "mkc_test_client_key_123",
            "--server-url",
            "http://localhost:8801/sse",
            "--config-path",
            str(config_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["client_api_key"] == "mkc_test_client_key_123"
    assert payload["server_url"] == "http://localhost:8801/sse"
    assert payload["default_headers"]["X-Minder-Client-Key"] == "mkc_test_client_key_123"

    output = capsys.readouterr().out
    assert "Stored client credentials" in output
    assert "MINDER_CLIENT_API_KEY" in output


def test_install_and_uninstall_local_mcp_configs(tmp_path, capsys) -> None:  # noqa: ANN001
    config_path = tmp_path / "client.json"
    config_path.write_text(
        json.dumps(
            {
                "client_api_key": "mkc_test_client_key_123",
                "server_url": "http://localhost:8801/sse",
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "install-mcp",
            "--config-path",
            str(config_path),
            "--cwd",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    vscode_payload = json.loads((tmp_path / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
    cursor_payload = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    claude_payload = json.loads((tmp_path / ".claude" / "mcp.json").read_text(encoding="utf-8"))

    assert vscode_payload["servers"]["minder"]["headers"]["X-Minder-Client-Key"] == "mkc_test_client_key_123"
    assert cursor_payload["mcpServers"]["minder"]["url"] == "http://localhost:8801/mcp"
    assert claude_payload["mcpServers"]["minder"]["url"] == "http://localhost:8801/sse"

    uninstall_exit = main(
        [
            "uninstall-mcp",
            "--cwd",
            str(tmp_path),
        ]
    )

    assert uninstall_exit == 0
    assert not (tmp_path / ".vscode" / "mcp.json").exists()
    assert not (tmp_path / ".cursor" / "mcp.json").exists()
    assert not (tmp_path / ".claude" / "mcp.json").exists()

    output = capsys.readouterr().out
    assert "Installed Minder MCP config" in output
    assert "Removed Minder MCP config" in output


def test_sync_dry_run_prints_delta_payload(tmp_path, monkeypatch, capsys) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "notes.md").write_text("# API\n\n- [ ] add sync docs\n", encoding="utf-8")
    (repo_root / "config.json").write_text('{"service":"minder","port":8801}', encoding="utf-8")
    config_path = tmp_path / "client.json"
    config_path.write_text(
        json.dumps(
            {
                "client_api_key": "mkc_test_client_key_123",
                "server_url": "http://localhost:8801/sse",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_repo_root", lambda path: Path(path).resolve())
    monkeypatch.setattr(cli, "_git_branch", lambda repo: "feature/sync")
    monkeypatch.setattr(
        cli,
        "_git_file_delta",
        lambda repo, diff_base=None: (["notes.md", "config.json"], ["removed.py"]),
    )

    exit_code = main(
        [
            "sync",
            "--repo-id",
            "11111111-1111-1111-1111-111111111111",
            "--repo-path",
            str(repo_root),
            "--config-path",
            str(config_path),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["branch"] == "feature/sync"
    assert payload["deleted_files"] == ["removed.py"]
    assert payload["sync_metadata"]["changed_files"] == ["config.json", "notes.md"]
    assert payload["sync_metadata"]["deleted_file_count"] == 1
    assert any(node["node_type"] == "file" and node["name"] == "notes.md" for node in payload["nodes"])
    assert any(node["node_type"] == "todo" and node["name"] == "notes.md::TODO:3" for node in payload["nodes"])


def test_global_target_paths_resolve_across_platforms(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(cli.Path, "home", lambda: Path("/home/tester"))

    monkeypatch.setattr(cli.platform, "system", lambda: "Darwin")
    assert cli._global_target_path("vscode") == Path("/home/tester/Library/Application Support/Code/User/mcp.json")
    assert cli._global_target_path("cursor") == Path("/home/tester/Library/Application Support/Cursor/User/mcp.json")
    assert cli._global_target_path("claude-code") == Path("/home/tester/.claude/mcp.json")

    monkeypatch.setattr(cli.platform, "system", lambda: "Linux")
    assert cli._global_target_path("vscode") == Path("/home/tester/.config/Code/User/mcp.json")
    assert cli._global_target_path("cursor") == Path("/home/tester/.config/Cursor/User/mcp.json")

    monkeypatch.setattr(cli.platform, "system", lambda: "Windows")
    monkeypatch.setattr(cli, "_appdata_dir", lambda: Path("C:/Users/tester/AppData/Roaming"))
    assert cli._global_target_path("vscode") == Path("C:/Users/tester/AppData/Roaming/Code/User/mcp.json")
    assert cli._global_target_path("cursor") == Path("C:/Users/tester/AppData/Roaming/Cursor/User/mcp.json")
    assert cli._global_target_path("claude-code") == Path("/home/tester/.claude/mcp.json")


def test_sync_posts_payload_to_server(tmp_path, monkeypatch, capsys) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "notes.md").write_text("# API\n\n- [ ] add sync docs\n", encoding="utf-8")
    config_path = tmp_path / "client.json"
    config_path.write_text(
        json.dumps(
            {
                "client_api_key": "mkc_test_client_key_123",
                "server_url": "http://localhost:8801/sse",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_repo_root", lambda path: Path(path).resolve())
    monkeypatch.setattr(cli, "_git_branch", lambda repo: "feature/sync")
    monkeypatch.setattr(cli, "_git_file_delta", lambda repo, diff_base=None: (["notes.md"], ["removed.py"]))
    monkeypatch.setattr(cli, "_maybe_print_upgrade_notice", lambda: None)

    captured: dict[str, object] = {}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "repo_id": "11111111-1111-1111-1111-111111111111",
                "nodes_upserted": 2,
                "edges_upserted": 0,
                "deleted_nodes": 1,
            }

    def _fake_post(url: str, *, headers: dict[str, str], json: dict[str, object], timeout: int) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(cli.httpx, "post", _fake_post)

    exit_code = main(
        [
            "sync",
            "--repo-id",
            "11111111-1111-1111-1111-111111111111",
            "--repo-path",
            str(repo_root),
            "--config-path",
            str(config_path),
        ]
    )

    assert exit_code == 0
    assert captured["url"] == "http://localhost:8801/v1/client/repositories/11111111-1111-1111-1111-111111111111/graph-sync"
    assert captured["headers"] == {"X-Minder-Client-Key": "mkc_test_client_key_123"}
    assert captured["timeout"] == 30
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["deleted_files"] == ["removed.py"]
    assert payload["sync_metadata"]["changed_files"] == ["notes.md"]

    output = json.loads(capsys.readouterr().out)
    assert output["deleted_nodes"] == 1
    assert output["nodes_upserted"] == 2


def test_sync_prints_upgrade_notice_when_newer_pypi_version_exists(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "notes.md").write_text("# API\n", encoding="utf-8")
    config_path = tmp_path / "client.json"
    config_path.write_text(
        json.dumps(
            {
                "client_api_key": "mkc_test_client_key_123",
                "server_url": "http://localhost:8801/sse",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_repo_root", lambda path: Path(path).resolve())
    monkeypatch.setattr(cli, "_git_branch", lambda repo: "feature/sync")
    monkeypatch.setattr(cli, "_git_file_delta", lambda repo, diff_base=None: (["notes.md"], []))
    monkeypatch.setattr(cli, "_installed_package_version", lambda: "0.1.0")
    monkeypatch.setattr(cli, "_latest_pypi_version", lambda: "0.2.0")

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True}

    monkeypatch.setattr(cli.httpx, "post", lambda *args, **kwargs: _FakeResponse())

    exit_code = main(
        [
            "sync",
            "--repo-id",
            "11111111-1111-1111-1111-111111111111",
            "--repo-path",
            str(repo_root),
            "--config-path",
            str(config_path),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "A newer minder CLI is available (0.1.0 -> 0.2.0)" in output


def test_sync_can_skip_upgrade_notice(tmp_path, monkeypatch, capsys) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "notes.md").write_text("# API\n", encoding="utf-8")
    config_path = tmp_path / "client.json"
    config_path.write_text(
        json.dumps(
            {
                "client_api_key": "mkc_test_client_key_123",
                "server_url": "http://localhost:8801/sse",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_repo_root", lambda path: Path(path).resolve())
    monkeypatch.setattr(cli, "_git_branch", lambda repo: "feature/sync")
    monkeypatch.setattr(cli, "_git_file_delta", lambda repo, diff_base=None: (["notes.md"], []))

    def _boom() -> None:
        raise AssertionError("upgrade check should be skipped")

    monkeypatch.setattr(cli, "_maybe_print_upgrade_notice", _boom)

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True}

    monkeypatch.setattr(cli.httpx, "post", lambda *args, **kwargs: _FakeResponse())

    exit_code = main(
        [
            "sync",
            "--repo-id",
            "11111111-1111-1111-1111-111111111111",
            "--repo-path",
            str(repo_root),
            "--config-path",
            str(config_path),
            "--skip-upgrade-check",
        ]
    )

    assert exit_code == 0
    assert "A newer minder CLI is available" not in capsys.readouterr().out