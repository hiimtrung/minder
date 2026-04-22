from __future__ import annotations

import json
from pathlib import Path

import minder.cli as cli
from minder.cli import main
import minder.presentation.cli.utils.git as cli_git
import minder.presentation.cli.utils.version as cli_version
import minder.presentation.cli.utils.common as cli_common
import minder.presentation.cli.commands.mcp as cli_mcp
import minder.presentation.cli.commands.ide as cli_ide
import minder.presentation.cli.commands.update as cli_update
import minder.presentation.cli.commands.sync as cli_sync


def test_login_persists_client_config(tmp_path, capsys) -> None:  # noqa: ANN001
    config_path = tmp_path / "client.json"

    exit_code = main(
        [
            "login",
            "--client-key",
            "mkc_test_client_key_123",
            "--protocol",
            "sse",
            "--server-url",
            "http://localhost:8801/sse",
            "--config-path",
            str(config_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["client_api_key"] == "mkc_test_client_key_123"
    assert payload["protocol"] == "sse"
    assert payload["server_url"] == "http://localhost:8801/sse"
    assert (
        payload["default_headers"]["X-Minder-Client-Key"] == "mkc_test_client_key_123"
    )

    output = capsys.readouterr().out
    assert "Stored client credentials" in output
    assert "MINDER_CLIENT_API_KEY" in output


def test_login_with_stdio_protocol_installs_stdio_mcp_entry(
    tmp_path, capsys
) -> None:  # noqa: ANN001
    config_path = tmp_path / "client.json"

    login_exit = main(
        [
            "login",
            "--client-key",
            "mkc_test_client_key_123",
            "--protocol",
            "stdio",
            "--config-path",
            str(config_path),
        ]
    )
    assert login_exit == 0

    install_exit = main(
        [
            "install",
            "mcp",
            "--config-path",
            str(config_path),
            "--cwd",
            str(tmp_path),
            "--target",
            "vscode",
        ]
    )
    assert install_exit == 0

    vscode_payload = json.loads(
        (tmp_path / ".vscode" / "mcp.json").read_text(encoding="utf-8")
    )
    minder = vscode_payload["servers"]["minder"]
    assert minder["type"] == "stdio"
    assert minder["command"] == "uv"
    assert minder["args"] == ["run", "python", "-m", "minder.server"]
    assert minder["env"]["MINDER_SERVER__TRANSPORT"] == "stdio"
    assert minder["env"]["MINDER_CLIENT_API_KEY"] == "mkc_test_client_key_123"

    output = capsys.readouterr().out
    assert "Protocol: stdio" in output


def test_install_and_uninstall_local_mcp_configs(
    tmp_path, capsys
) -> None:  # noqa: ANN001
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
            "install",
            "mcp",
            "--config-path",
            str(config_path),
            "--cwd",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    vscode_payload = json.loads(
        (tmp_path / ".vscode" / "mcp.json").read_text(encoding="utf-8")
    )
    cursor_payload = json.loads(
        (tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8")
    )
    claude_payload = json.loads(
        (tmp_path / ".claude" / "mcp.json").read_text(encoding="utf-8")
    )

    assert (
        vscode_payload["servers"]["minder"]["headers"]["X-Minder-Client-Key"]
        == "mkc_test_client_key_123"
    )
    assert cursor_payload["mcpServers"]["minder"]["url"] == "http://localhost:8801/mcp"
    assert claude_payload["mcpServers"]["minder"]["url"] == "http://localhost:8801/sse"

    uninstall_exit = main(
        [
            "uninstall",
            "mcp",
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


def test_install_ide_creates_repo_local_assets_and_gitignore(
    tmp_path, capsys
) -> None:  # noqa: ANN001
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
            "install",
            "ide",
            "--config-path",
            str(config_path),
            "--cwd",
            str(tmp_path),
            "--target",
            "vscode",
            "--target",
            "claude-code",
        ]
    )

    assert exit_code == 0
    vscode_payload = json.loads(
        (tmp_path / ".vscode" / "mcp.json").read_text(encoding="utf-8")
    )
    assert (
        vscode_payload["servers"]["minder"]["headers"]["X-Minder-Client-Key"]
        == "mkc_test_client_key_123"
    )
    assert "Minder repo-local instructions" in (
        tmp_path / ".github" / "copilot-instructions.md"
    ).read_text(encoding="utf-8")
    assert "minder-repo-guide" in (
        tmp_path / ".claude" / "agents" / "minder-repo-guide.md"
    ).read_text(encoding="utf-8")
    assert "Minder repo-local instructions" in (tmp_path / "CLAUDE.md").read_text(
        encoding="utf-8"
    )
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".vscode/mcp.json" in gitignore
    assert ".claude/mcp.json" in gitignore
    assert ".minder/" in gitignore

    metadata = json.loads(
        (tmp_path / ".minder" / "ide-bootstrap.json").read_text(encoding="utf-8")
    )
    assert metadata["targets"] == ["vscode", "claude-code"]

    output = capsys.readouterr().out
    assert "Installed Minder IDE asset" in output


def test_install_ide_updates_managed_blocks_without_removing_custom_text(
    tmp_path,
) -> None:  # noqa: ANN001
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
    claude_file = tmp_path / "CLAUDE.md"
    claude_file.write_text(
        "Custom project notes\n\n<!-- minder:begin minder-ide-instructions:claude-code -->\noutdated\n<!-- minder:end minder-ide-instructions:claude-code -->\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "install",
            "ide",
            "--config-path",
            str(config_path),
            "--cwd",
            str(tmp_path),
            "--target",
            "claude-code",
        ]
    )

    assert exit_code == 0
    content = claude_file.read_text(encoding="utf-8")
    assert "Custom project notes" in content
    assert content.count("minder:begin minder-ide-instructions:claude-code") == 1
    assert "outdated" not in content


def test_uninstall_ide_removes_managed_assets(tmp_path, capsys) -> None:  # noqa: ANN001
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
    (tmp_path / ".gitignore").write_text("dist/\n", encoding="utf-8")

    install_exit = main(
        [
            "install",
            "ide",
            "--config-path",
            str(config_path),
            "--cwd",
            str(tmp_path),
            "--target",
            "cursor",
            "--target",
            "claude-code",
        ]
    )
    assert install_exit == 0

    uninstall_exit = main(
        [
            "uninstall",
            "ide",
            "--cwd",
            str(tmp_path),
            "--target",
            "cursor",
            "--target",
            "claude-code",
        ]
    )

    assert uninstall_exit == 0
    assert not (tmp_path / ".cursor" / "mcp.json").exists()
    assert not (tmp_path / ".claude" / "mcp.json").exists()
    assert not (tmp_path / ".cursor" / "rules" / "minder.mdc").exists()
    assert not (tmp_path / ".claude" / "agents" / "minder-repo-guide.md").exists()
    assert not (tmp_path / ".minder" / "ide-bootstrap.json").exists()
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert gitignore == "dist/\n"

    output = capsys.readouterr().out
    assert "Removed Minder IDE asset" in output


def test_check_update_reports_cli_and_server_versions(
    tmp_path, monkeypatch, capsys
) -> None:  # noqa: ANN001
    install_dir = tmp_path / "release"
    install_dir.mkdir()
    (install_dir / ".env").write_text(
        "MINDER_API_IMAGE=ghcr.io/hiimtrung/minder-api:v0.1.0\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("MINDER_INSTALL_DIR", str(install_dir))
    monkeypatch.setattr("minder.presentation.cli.utils.version.installed_package_version", lambda: "0.1.0")
    monkeypatch.setattr("minder.presentation.cli.utils.version.latest_pypi_version", lambda: "0.2.0")
    monkeypatch.setattr(cli_update, "installed_package_version", lambda: "0.1.0")
    monkeypatch.setattr(cli_update, "latest_pypi_version", lambda: "0.2.0")
    monkeypatch.setattr(
        cli_update,
        "_latest_github_release",
        lambda slug: {
            "version": "v0.2.0",
            "url": f"https://github.com/{slug}/releases/tag/v0.2.0",
        },
    )

    exit_code = main(["update", "--check", "--component", "all"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "CLI update status:" in output
    assert "status: update available (0.1.0 -> 0.2.0)" in output
    assert "Server update status:" in output
    assert "status: update available (v0.1.0 -> v0.2.0)" in output


def test_check_version_reports_installed_and_latest(
    monkeypatch, capsys
) -> None:  # noqa: ANN001
    monkeypatch.setattr("minder.presentation.cli.utils.version.installed_package_version", lambda: "0.3.2")
    monkeypatch.setattr("minder.presentation.cli.utils.version.latest_pypi_version", lambda: "0.3.4")
    monkeypatch.setattr(cli_update, "installed_package_version", lambda: "0.3.2")
    monkeypatch.setattr(cli_update, "latest_pypi_version", lambda: "0.3.4")

    exit_code = main(["version", "--check"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "CLI version:" in output
    assert "installed: 0.3.2" in output
    assert "latest: 0.3.4" in output
    assert "status: update available (0.3.2 -> 0.3.4)" in output


def test_update_cli_uses_available_manager(
    monkeypatch, capsys
) -> None:  # noqa: ANN001
    captured: dict[str, object] = {}

    class _Result:
        returncode = 0
        stdout = "updated"
        stderr = ""

    monkeypatch.setattr(cli_update.shutil, "which", lambda name: f"/usr/bin/{name}")

    def _fake_run(command, capture_output, text, check):  # noqa: ANN001
        captured["command"] = command
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["check"] = check
        return _Result()

    monkeypatch.setattr(cli_update.subprocess, "run", _fake_run)

    exit_code = main(["update", "--component", "cli", "--manager", "uv"])

    assert exit_code == 0
    assert captured["command"] == ["uv", "tool", "upgrade", "minder"]
    output = capsys.readouterr().out
    assert "CLI update completed:" in output
    assert "via uv tool upgrade minder" in output


def test_update_server_downloads_release_installer_and_reuses_env(
    tmp_path, monkeypatch, capsys
) -> None:  # noqa: ANN001
    install_dir = tmp_path / "release"
    install_dir.mkdir()
    (install_dir / ".env").write_text(
        "MINDER_PORT=8800\nMILVUS_PORT=19530\nMINDER_MODELS_DIR=/models\nOPENAI_API_KEY=test-key\nMINDER_API_IMAGE=ghcr.io/hiimtrung/minder-api:v0.1.0\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli_update,
        "_latest_github_release",
        lambda slug: {
            "version": "v0.2.0",
            "url": f"https://github.com/{slug}/releases/tag/v0.2.0",
        },
    )

    class _HttpResponse:
        text = "#!/usr/bin/env bash\necho server-updated\n"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(cli_update.httpx, "get", lambda url, timeout: _HttpResponse())

    captured: dict[str, object] = {}

    class _RunResult:
        returncode = 0
        stdout = "server-updated\n"
        stderr = ""

    def _fake_run(command, input, capture_output, text, env, check):  # noqa: ANN001
        captured["command"] = command
        captured["input"] = input
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["env"] = env
        captured["check"] = check
        return _RunResult()

    monkeypatch.setattr(cli_update.subprocess, "run", _fake_run)

    exit_code = main(
        ["update", "--component", "server", "--install-dir", str(install_dir)]
    )

    assert exit_code == 0
    assert captured["command"] == ["bash", "-"]
    assert captured["input"] == "#!/usr/bin/env bash\necho server-updated\n"
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["MINDER_INSTALL_DIR"] == str(install_dir)
    assert env["MINDER_MODELS_DIR"] == "/models"
    assert env["MINDER_PORT"] == "8800"
    assert env["MILVUS_PORT"] == "19530"
    assert env["OPENAI_API_KEY"] == "test-key"
    output = capsys.readouterr().out
    assert "Server update completed" in output
    assert "Rollback guidance" in output


def test_sync_dry_run_prints_delta_payload(
    tmp_path, monkeypatch, capsys
) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "notes.md").write_text(
        "# API\n\n- [ ] add sync docs\n", encoding="utf-8"
    )
    (repo_root / "config.json").write_text(
        '{"service":"minder","port":8801}', encoding="utf-8"
    )
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

    monkeypatch.setattr(cli_sync, "repo_root", lambda path: Path(path).resolve())
    monkeypatch.setattr(cli_sync, "git_branch", lambda repo: "feature/sync")
    monkeypatch.setattr(
        cli_sync,
        "git_file_delta",
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
    assert any(
        node["node_type"] == "file" and node["name"] == "notes.md"
        for node in payload["nodes"]
    )
    assert any(
        node["node_type"] == "todo" and node["name"] == "notes.md::TODO:3"
        for node in payload["nodes"]
    )


def test_global_target_paths_resolve_across_platforms(
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setattr("pathlib.Path.home", lambda: Path("/home/tester"))

    monkeypatch.setattr(cli_mcp.platform, "system", lambda: "Darwin")
    assert cli_mcp._global_target_path("vscode") == Path(
        "/home/tester/Library/Application Support/Code/User/globalStorage/mcp-servers.json"
    )
    assert cli_mcp._global_target_path("cursor") == Path(
        "/home/tester/Library/Application Support/Cursor/User/globalStorage/mcp-servers.json"
    )
    assert cli_mcp._global_target_path("claude-code") == Path(
        "/home/tester/Library/Application Support/Claude/claude_desktop_config.json"
    )

    monkeypatch.setattr(cli_mcp.platform, "system", lambda: "Linux")
    assert cli_mcp._global_target_path("vscode") == Path(
        "/home/tester/.config/Code/User/globalStorage/mcp-servers.json"
    )
    assert cli_mcp._global_target_path("cursor") == Path(
        "/home/tester/.config/Cursor/User/globalStorage/mcp-servers.json"
    )

    monkeypatch.setattr(cli_mcp.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        cli_mcp, "appdata_dir", lambda: Path("C:/Users/tester/AppData/Roaming")
    )
    assert cli_mcp._global_target_path("vscode") == Path(
        "C:/Users/tester/AppData/Roaming/Code/User/globalStorage/mcp-servers.json"
    )
    assert cli_mcp._global_target_path("cursor") == Path(
        "C:/Users/tester/AppData/Roaming/Cursor/User/globalStorage/mcp-servers.json"
    )
    assert cli_mcp._global_target_path("claude-code") == Path(
        "C:/Users/tester/AppData/Roaming/Claude/claude_desktop_config.json"
    )


def test_sync_posts_payload_to_server(
    tmp_path, monkeypatch, capsys
) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "notes.md").write_text(
        "# API\n\n- [ ] add sync docs\n", encoding="utf-8"
    )
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

    monkeypatch.setattr(cli_sync, "repo_root", lambda path: Path(path).resolve())
    monkeypatch.setattr(cli_sync, "git_branch", lambda repo: "feature/sync")
    monkeypatch.setattr(
        cli_sync,
        "git_file_delta",
        lambda repo, diff_base=None: (["notes.md"], ["removed.py"]),
    )
    monkeypatch.setattr(cli_sync, "maybe_print_upgrade_notice", lambda: None)

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

    def _fake_post(
        url: str, *, headers: dict[str, str], json: dict[str, object], timeout: int
    ) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(cli_sync.httpx, "post", _fake_post)

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
    assert (
        captured["url"]
        == "http://localhost:8801/v1/client/repositories/11111111-1111-1111-1111-111111111111/graph-sync"
    )
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

    monkeypatch.setattr(cli_sync, "repo_root", lambda path: Path(path).resolve())
    monkeypatch.setattr(cli_sync, "git_branch", lambda repo: "feature/sync")
    monkeypatch.setattr(
        cli_sync, "git_file_delta", lambda repo, diff_base=None: (["notes.md"], [])
    )
    monkeypatch.setattr("minder.presentation.cli.utils.version.installed_package_version", lambda: "0.1.0")
    monkeypatch.setattr("minder.presentation.cli.utils.version.latest_pypi_version", lambda: "0.2.0")
    monkeypatch.setattr(cli_update, "installed_package_version", lambda: "0.1.0")
    monkeypatch.setattr(cli_update, "latest_pypi_version", lambda: "0.2.0")

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True}

    monkeypatch.setattr(cli_sync.httpx, "post", lambda *args, **kwargs: _FakeResponse())

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


def test_sync_auto_resolves_repo_id_when_omitted(
    tmp_path, monkeypatch, capsys
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

    monkeypatch.setattr(cli_sync, "repo_root", lambda path: Path(path).resolve())
    monkeypatch.setattr(cli_sync, "git_branch", lambda repo: "develop")
    monkeypatch.setattr(
        cli_sync, "git_remote_url", lambda repo: "git@github.com:example/minder.git"
    )
    monkeypatch.setattr(
        cli_sync, "git_file_delta", lambda repo, diff_base=None: (["notes.md"], [])
    )
    monkeypatch.setattr(cli_sync, "maybe_print_upgrade_notice", lambda: None)

    captured: list[dict[str, object]] = []

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    def _fake_post(
        url: str, *, headers: dict[str, str], json: dict[str, object], timeout: int
    ) -> _FakeResponse:
        captured.append(
            {"url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        if url.endswith("/v1/client/repositories/resolve"):
            return _FakeResponse(
                {
                    "created": False,
                    "repository": {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "name": "repo",
                        "path": str(repo_root / ".minder"),
                        "workflow_name": None,
                        "workflow_state": None,
                        "current_step": None,
                        "created_at": None,
                    },
                }
            )
        return _FakeResponse(
            {"repo_id": "22222222-2222-2222-2222-222222222222", "nodes_upserted": 1}
        )

    monkeypatch.setattr(cli_sync.httpx, "post", _fake_post)

    exit_code = main(
        [
            "sync",
            "--repo-path",
            str(repo_root),
            "--config-path",
            str(config_path),
        ]
    )

    assert exit_code == 0
    assert captured[0]["url"] == "http://localhost:8801/v1/client/repositories/resolve"
    assert (
        captured[1]["url"]
        == "http://localhost:8801/v1/client/repositories/22222222-2222-2222-2222-222222222222/graph-sync"
    )
    assert captured[0]["timeout"] == 15
    assert captured[1]["timeout"] == 30
    assert captured[0]["json"] == {
        "repo_name": "minder",
        "repo_path": str(repo_root),
        "repo_url": "git@github.com:example/minder.git",
        "default_branch": "develop",
    }

    output = json.loads(capsys.readouterr().out)
    assert output["repo_id"] == "22222222-2222-2222-2222-222222222222"


def test_sync_requires_remote_origin_when_repo_id_omitted(
    tmp_path, monkeypatch
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

    monkeypatch.setattr(cli_sync, "repo_root", lambda path: Path(path).resolve())
    monkeypatch.setattr(cli_sync, "git_branch", lambda repo: "develop")
    monkeypatch.setattr(cli_sync, "git_remote_url", lambda repo: None)
    monkeypatch.setattr(
        cli_sync, "git_file_delta", lambda repo, diff_base=None: (["notes.md"], [])
    )
    monkeypatch.setattr(cli_sync, "maybe_print_upgrade_notice", lambda: None)

    try:
        main(
            [
                "sync",
                "--repo-path",
                str(repo_root),
                "--config-path",
                str(config_path),
            ]
        )
    except ValueError as exc:
        assert (
            str(exc)
            == "Repository remote origin SSH URL is required when --repo-id is omitted"
        )
    else:
        raise AssertionError(
            "sync should require a remote origin when repo_id is omitted"
        )


def test_sync_can_skip_upgrade_notice(
    tmp_path, monkeypatch, capsys
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

    monkeypatch.setattr(cli_sync, "repo_root", lambda path: Path(path).resolve())
    monkeypatch.setattr(cli_sync, "git_branch", lambda repo: "feature/sync")
    monkeypatch.setattr(
        cli_sync, "git_file_delta", lambda repo, diff_base=None: (["notes.md"], [])
    )

    def _boom() -> None:
        raise AssertionError("upgrade check should be skipped")

    monkeypatch.setattr(cli_sync, "maybe_print_upgrade_notice", _boom)

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True}

    monkeypatch.setattr(cli_sync.httpx, "post", lambda *args, **kwargs: _FakeResponse())

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


def test_detect_branch_relationships_from_gitmodules(tmp_path) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".gitmodules").write_text(
        '[submodule "vendor/other"]\n'
        "\tpath = vendor/other\n"
        "\turl = git@github.com:example/other.git\n"
        "\tbranch = release/1.0\n"
        '[submodule "vendor/no_url"]\n'
        "\tpath = vendor/no_url\n",
        encoding="utf-8",
    )

    relationships = cli_git.detect_branch_relationships(repo_root, "feature/sync")

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship["source_branch"] == "feature/sync"
    assert relationship["target_repo_name"] == "other"
    assert relationship["target_repo_url"] == "git@github.com:example/other.git"
    assert relationship["target_branch"] == "release/1.0"
    assert relationship["relation"] == "depends_on"
    assert relationship["direction"] == "outbound"
    assert relationship["metadata"]["source"] == "gitmodules"
    assert relationship["metadata"]["submodule_path"] == "vendor/other"


def test_detect_branch_relationships_merges_override_file(tmp_path) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    (repo_root / ".minder").mkdir(parents=True)
    (repo_root / ".gitmodules").write_text(
        '[submodule "vendor/other"]\n'
        "\tpath = vendor/other\n"
        "\turl = git@github.com:example/other.git\n"
        "\tbranch = main\n",
        encoding="utf-8",
    )
    (repo_root / ".minder" / "branch-topology.toml").write_text(
        "[[branch_relationships]]\n"
        'source_branch = "develop"\n'
        'target_repo_name = "sibling-service"\n'
        'target_repo_url = "https://github.com/example/sibling.git"\n'
        'target_branch = "develop"\n'
        'relation = "consumes"\n'
        'direction = "inbound"\n'
        "confidence = 0.8\n"
        "[branch_relationships.metadata]\n"
        'reason = "shared bus"\n',
        encoding="utf-8",
    )

    relationships = cli_git.detect_branch_relationships(repo_root, "feature/sync")

    assert {entry["target_repo_name"] for entry in relationships} == {
        "other",
        "sibling-service",
    }
    override = next(
        entry
        for entry in relationships
        if entry["target_repo_name"] == "sibling-service"
    )
    assert override["source_branch"] == "develop"
    assert override["relation"] == "consumes"
    assert override["direction"] == "inbound"
    assert override["confidence"] == 0.8
    assert override["target_repo_url"] == "git@github.com:example/sibling.git"
    assert override["metadata"]["reason"] == "shared bus"
    assert override["metadata"]["source"] == "branch-topology.toml"


def test_detect_branch_relationships_dedupes_submodule_and_override(tmp_path) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    (repo_root / ".minder").mkdir(parents=True)
    (repo_root / ".gitmodules").write_text(
        '[submodule "vendor/other"]\n'
        "\tpath = vendor/other\n"
        "\turl = git@github.com:example/other.git\n"
        "\tbranch = main\n",
        encoding="utf-8",
    )
    (repo_root / ".minder" / "branch-topology.toml").write_text(
        "[[branch_relationships]]\n"
        'source_branch = "feature/sync"\n'
        'target_repo_name = "other"\n'
        'target_repo_url = "git@github.com:example/other.git"\n'
        'target_branch = "main"\n'
        'relation = "depends_on"\n'
        "confidence = 1.0\n"
        "[branch_relationships.metadata]\n"
        'note = "promoted manually"\n',
        encoding="utf-8",
    )

    relationships = cli_git.detect_branch_relationships(repo_root, "feature/sync")

    assert len(relationships) == 1
    relationship = relationships[0]
    # submodule metadata is preserved, override metadata is merged in
    assert relationship["metadata"]["note"] == "promoted manually"
    assert relationship["metadata"]["source"] == "branch-topology.toml"
    assert relationship["metadata"]["submodule_path"] == "vendor/other"


def test_update_server_uses_powershell_installer_on_windows(
    tmp_path, monkeypatch, capsys
) -> None:  # noqa: ANN001
    install_dir = tmp_path / "release"
    install_dir.mkdir()
    (install_dir / ".env").write_text(
        "MINDER_PORT=8800\nMINDER_API_IMAGE=ghcr.io/hiimtrung/minder-api:v0.1.0\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr(
        cli_update,
        "_latest_github_release",
        lambda slug: {
            "version": "v0.2.0",
            "url": f"https://github.com/{slug}/releases/tag/v0.2.0",
        },
    )

    class _HttpResponse:
        text = "Write-Host 'server-updated'"

        def raise_for_status(self) -> None:
            return None

    captured_urls: list[str] = []

    def _fake_get(url: str, timeout: int) -> _HttpResponse:
        captured_urls.append(url)
        return _HttpResponse()

    monkeypatch.setattr(cli_update.httpx, "get", _fake_get)

    captured: dict[str, object] = {}

    class _RunResult:
        returncode = 0
        stdout = "server-updated"
        stderr = ""

    def _fake_run(command, input, capture_output, text, env, check):  # noqa: ANN001
        captured["command"] = command
        captured["input"] = input
        captured["env"] = env
        return _RunResult()

    monkeypatch.setattr(cli_update.subprocess, "run", _fake_run)

    exit_code = main(
        [
            "update",
            "--component",
            "server",
            "--install-dir",
            str(install_dir),
        ]
    )

    assert exit_code == 0
    assert any(url.endswith(".ps1") for url in captured_urls)
    command = captured["command"]
    assert isinstance(command, list)
    assert command[0] == "powershell.exe"
    assert "-ExecutionPolicy" in command
    assert "Bypass" in command
    assert captured["input"] == "Write-Host 'server-updated'"
    output = capsys.readouterr().out
    assert "install-minder-v0.2.0.ps1" in output


def test_sync_dry_run_includes_branch_relationships(tmp_path, monkeypatch, capsys) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    (repo_root / ".minder").mkdir(parents=True)
    (repo_root / "notes.md").write_text("# API\n", encoding="utf-8")
    (repo_root / ".gitmodules").write_text(
        '[submodule "vendor/other"]\n'
        "\tpath = vendor/other\n"
        "\turl = git@github.com:example/other.git\n"
        "\tbranch = main\n",
        encoding="utf-8",
    )
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

    monkeypatch.setattr(cli_sync, "repo_root", lambda path: Path(path).resolve())
    monkeypatch.setattr(cli_sync, "git_branch", lambda repo: "feature/sync")
    monkeypatch.setattr(
        cli_sync,
        "git_file_delta",
        lambda repo, diff_base=None: (["notes.md"], []),
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
    assert payload["sync_metadata"]["branch_relationship_count"] == 1
    assert len(payload["branch_relationships"]) == 1
    relationship = payload["branch_relationships"][0]
    assert relationship["source_branch"] == "feature/sync"
    assert relationship["target_repo_name"] == "other"
    assert relationship["target_branch"] == "main"
    assert relationship["metadata"]["source"] == "gitmodules"
