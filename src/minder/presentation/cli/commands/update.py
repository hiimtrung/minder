from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

import httpx

from ..utils.version import (
    installed_package_version,
    latest_pypi_version,
    cli_update_available,
    parse_version,
)

_GITHUB_RELEASE_REPOSITORY_API = "https://api.github.com/repos"


def version_command(args: argparse.Namespace) -> int:
    """Show the Minder CLI version."""
    version = installed_package_version()
    if version:
        print(f"CLI version: {version}")
        print(f"  installed: {version}")
        
        # If check-version style requested or via flag
        if getattr(args, "check", False):
            latest = latest_pypi_version()
            print(f"  latest: {latest or 'unknown'}")
            if latest and parse_version(latest) > parse_version(version):
                print(f"  status: update available ({version} -> {latest})")
            else:
                print("  status: up to date")
    else:
        print("minder version unknown (not installed as a package)")
    return 0


def check_version_command(args: argparse.Namespace) -> int:
    """Show installed CLI version and latest published version."""
    args.check = True
    return version_command(args)


def _latest_github_release(repository_slug: str) -> dict[str, str] | None:
    try:
        response = httpx.get(
            f"{_GITHUB_RELEASE_REPOSITORY_API}/{repository_slug}/releases/latest",
            timeout=5,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        payload = response.json()
        tag_name = payload.get("tag_name")
        html_url = payload.get("html_url")
        if tag_name:
            return {"version": tag_name, "url": html_url or ""}
    except Exception:
        pass
    return None


def check_update_command(args: argparse.Namespace) -> int:
    """Check for newer published Minder CLI and server releases."""
    component = args.component
    
    if component in {"cli", "all"}:
        installed, latest, has_update = cli_update_available()
        print("CLI update status:")
        print(f"  installed: {installed or 'unknown'}")
        print(f"  latest: {latest or 'unknown'}")
        status = f"update available ({installed} -> {latest})" if has_update else "up to date"
        print(f"  status: {status}")
        
    if component in {"server", "all"}:
        # Simplified server check for now
        print("\nServer update status:")
        try:
            from ..utils.common import load_env_file
            # Check install_dir from args, then MINDER_INSTALL_DIR env, then current dir
            install_dir_str = getattr(args, "install_dir", None) or os.getenv("MINDER_INSTALL_DIR") or "."
            install_dir = Path(install_dir_str).expanduser().resolve()
            env_file = install_dir / ".env"
            env = load_env_file(env_file)
            current_image = env.get("MINDER_API_IMAGE", "")
            current_version = current_image.partition(":")[-1] or "unknown"
            if current_version != "unknown" and not current_version.startswith("v"):
                current_version = "v" + current_version
            
            release = _latest_github_release("hiimtrung/minder")
            latest_version = release["version"] if release else "unknown"
            if latest_version != "unknown" and not latest_version.startswith("v"):
                latest_version = "v" + latest_version
            
            print(f"  installed: {current_version}")
            print(f"  latest: {latest_version}")
            if current_version != "unknown" and latest_version != "unknown" and current_version != latest_version:
                print(f"  status: update available ({current_version} -> {latest_version})")
            else:
                print("  status: up to date")
        except Exception as e:
            print(f"  status: unknown ({e})")
        
    return 0


def _cli_update_commands(manager: str) -> list[list[str]]:
    if manager == "uv":
        return [["uv", "tool", "upgrade", "minder"]]
    if manager == "pipx":
        return [["pipx", "upgrade", "minder"]]
    if manager == "pip":
        return [[sys.executable, "-m", "pip", "install", "--upgrade", "minder"]]
    return [
        ["uv", "tool", "upgrade", "minder"],
        ["pipx", "upgrade", "minder"],
        [sys.executable, "-m", "pip", "install", "--upgrade", "minder"],
    ]


def _self_update_cli(manager: str) -> None:
    before_version = installed_package_version()
    target_version = latest_pypi_version()
    failures: list[str] = []
    for command in _cli_update_commands(manager):
        executable = command[0]
        if executable != sys.executable and shutil.which(executable) is None:
            failures.append(f"{' '.join(command)} -> command not available")
            continue
        print(f"Executing CLI update: {' '.join(command)}")
        result = subprocess.run(
            command,
            capture_output=False,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            after_version = installed_package_version() or target_version
            print(
                "CLI update completed: "
                f"{before_version or 'unknown'} -> {after_version or 'unknown'} "
                f"via {' '.join(command)}"
            )
            return
        failures.append(f"{' '.join(command)} -> failed with exit code {result.returncode}")
    raise RuntimeError("CLI update failed: " + "; ".join(failures))


def _self_update_server(install_dir: Path) -> None:
    if not install_dir.is_dir():
        raise ValueError(f"Server installation directory not found: {install_dir}")

    env_file = install_dir / ".env"
    if not env_file.is_file():
        raise ValueError(f"Server .env file not found in {install_dir}")

    release = _latest_github_release("hiimtrung/minder")
    if not release:
        raise RuntimeError("Could not find latest Minder release on GitHub")

    version = release["version"]
    print(f"Updating Minder server to {version}...")

    is_windows = sys.platform == "win32"
    installer_ext = "ps1" if is_windows else "sh"
    installer_url = f"https://raw.githubusercontent.com/hiimtrung/minder/main/install-minder-{version}.{installer_ext}"

    print(f"Downloading installer from {installer_url}...")
    response = httpx.get(installer_url, timeout=30)
    response.raise_for_status()
    installer_script = response.text

    if is_windows:
        command = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", "-"]
    else:
        command = ["bash", "-"]

    print("Executing server update script...")
    env_vars = {"MINDER_INSTALL_DIR": str(install_dir.resolve())}
    if env_file.is_file():
        from ..utils.common import load_env_file
        env_vars.update(load_env_file(env_file))
            
    result = subprocess.run(
        command,
        input=installer_script,
        capture_output=True,
        text=True,
        env=env_vars,
        check=True,
    )
    print(result.stdout)
    print(f"Server update completed: Minder server updated to {version}")
    print(f"Rollback guidance: To revert, run the installer with the previous version tag.")


def update_command(args: argparse.Namespace) -> int:
    """Apply an update for the Minder CLI, server deployment, or both."""
    component = args.component
    manager = args.manager
    
    if component in {"cli", "all"}:
        try:
            _self_update_cli(manager)
        except Exception as e:
            print(f"CLI update failed: {e}")
            if component == "cli":
                return 1
            
    if component in {"server", "all"}:
        install_dir = Path(args.install_dir).expanduser().resolve()
        try:
            _self_update_server(install_dir)
        except Exception as e:
            print(f"Server update failed: {e}")
            return 1
        
    return 0
