from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_WATCH_INTERVAL_SECONDS = 0.75
WATCHED_CONFIG_FILES = (".env", "minder.toml")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_dev_command() -> list[str]:
    return [sys.executable, "-m", "minder.server"]


def build_dev_env(
    root: Path,
    *,
    transport: str = "sse",
    port: int | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(root / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    pythonpath_parts = [part for part in existing_pythonpath.split(os.pathsep) if part]
    if src_path not in pythonpath_parts:
        pythonpath_parts.insert(0, src_path)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    env.setdefault("UV_CACHE_DIR", ".uv-cache")
    env["MINDER_SERVER__TRANSPORT"] = transport
    if port is not None:
        env["MINDER_SERVER__PORT"] = str(port)
    return env


def collect_watch_files(root: Path) -> list[Path]:
    watched_files: list[Path] = []
    src_root = root / "src"
    if src_root.exists():
        watched_files.extend(sorted(path for path in src_root.rglob("*.py") if path.is_file()))
    for config_name in WATCHED_CONFIG_FILES:
        config_path = root / config_name
        if config_path.is_file():
            watched_files.append(config_path)
    return watched_files


def snapshot_mtimes(paths: list[Path]) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for path in paths:
        if path.exists():
            snapshot[str(path)] = path.stat().st_mtime
    return snapshot


def start_server_process(root: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(build_dev_command(), cwd=root, env=env)


def stop_server_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_dev_server(
    *,
    transport: str = "sse",
    port: int | None = None,
    interval_seconds: float = DEFAULT_WATCH_INTERVAL_SECONDS,
) -> int:
    root = repo_root()
    env = build_dev_env(root, transport=transport, port=port)
    print(
        "Starting Minder dev server with hot reload "
        f"(transport={transport}, port={env.get('MINDER_SERVER__PORT', 'default')}).",
        flush=True,
    )
    print(f"Watching {root / 'src'} plus {', '.join(WATCHED_CONFIG_FILES)} for changes.", flush=True)
    print("Run with uv run python scripts/dev_server.py", flush=True)

    process = start_server_process(root, env)
    previous_snapshot = snapshot_mtimes(collect_watch_files(root))
    exit_code: int = 0
    exit_reported = False

    try:
        while True:
            time.sleep(interval_seconds)
            current_snapshot = snapshot_mtimes(collect_watch_files(root))
            if current_snapshot != previous_snapshot:
                previous_snapshot = current_snapshot
                print("Source change detected. Restarting Minder...", flush=True)
                stop_server_process(process)
                process = start_server_process(root, env)
                exit_reported = False
                continue

            current_return_code = process.poll()
            if current_return_code is not None:
                exit_code = current_return_code
                if not exit_reported:
                    print(
                        f"Minder dev server exited with code {current_return_code}. "
                        "Waiting for the next file change to restart.",
                        flush=True,
                    )
                    exit_reported = True
    except KeyboardInterrupt:
        print("Stopping Minder dev server...", flush=True)
    finally:
        stop_server_process(process)
    return exit_code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Minder in dev mode with hot reload.")
    parser.add_argument(
        "--transport",
        default="sse",
        choices=("sse", "stdio"),
        help="Transport to run during development. Defaults to sse.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override the Minder server port for the dev process.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_WATCH_INTERVAL_SECONDS,
        help="Polling interval in seconds for file watching.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_dev_server(
        transport=args.transport,
        port=args.port,
        interval_seconds=args.interval,
    )


if __name__ == "__main__":
    raise SystemExit(main())