from __future__ import annotations

import os
from pathlib import Path

from minder.dev import build_dev_command, build_dev_env, collect_watch_files, snapshot_mtimes


def test_build_dev_command_targets_minder_server_module() -> None:
    command = build_dev_command()
    assert command[-2:] == ["-m", "minder.server"]


def test_build_dev_env_prepends_src_and_sets_dev_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYTHONPATH", "/existing/path")

    env = build_dev_env(tmp_path, transport="sse", port=9900)

    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(tmp_path / "src")
    assert "/existing/path" in env["PYTHONPATH"].split(os.pathsep)
    assert env["UV_CACHE_DIR"] == ".uv-cache"
    assert env["MINDER_SERVER__TRANSPORT"] == "sse"
    assert env["MINDER_SERVER__PORT"] == "9900"


def test_collect_watch_files_includes_python_sources_and_config_files(tmp_path: Path) -> None:
    src_dir = tmp_path / "src" / "minder"
    src_dir.mkdir(parents=True)
    python_file = src_dir / "server.py"
    python_file.write_text("print('ok')\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("MINDER_SERVER__PORT=8800\n", encoding="utf-8")
    toml_file = tmp_path / "minder.toml"
    toml_file.write_text("[server]\nport=8800\n", encoding="utf-8")

    watched = collect_watch_files(tmp_path)

    assert python_file in watched
    assert env_file in watched
    assert toml_file in watched


def test_snapshot_mtimes_tracks_existing_paths(tmp_path: Path) -> None:
    file_path = tmp_path / "tracked.py"
    file_path.write_text("print('tracked')\n", encoding="utf-8")

    snapshot = snapshot_mtimes([file_path, tmp_path / "missing.py"])

    assert str(file_path) in snapshot
    assert str(tmp_path / "missing.py") not in snapshot