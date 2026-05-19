from __future__ import annotations

import argparse

from .utils.version import installed_package_version
from .utils.common import client_config_path
from .commands.auth import login_command
from .commands.mcp import install_mcp_command, uninstall_mcp_command, remove_mcp_command, _global_target_path
from .commands.update import version_command, check_update_command, update_command
from .commands.sync import sync_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minder",
        description="Minder CLI — repo sync, MCP config, and auth for Minder Server.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"minder {installed_package_version() or 'dev'}",
    )

    subparsers = parser.add_subparsers(dest="command", title="commands", metavar="<command>")

    # ── Auth ─────────────────────────────────────────────────────────────────
    login = subparsers.add_parser("login", help="Authenticate with Minder server.")
    login.add_argument("--client-key", help="Client API key (mkc_...).")
    login.add_argument("--protocol", choices=("sse", "stdio"), help="Transport protocol.")
    login.add_argument("--server-url", help="Minder server URL.")
    login.add_argument("--config-path", default=str(client_config_path()), help="Path to save config.")
    login.set_defaults(func=login_command)

    # ── MCP config install / uninstall ────────────────────────────────────────
    _cwd_placeholder = "<repo>"
    _mcp_epilog = (
        "targets:\n"
        f"  vscode       per-repo:  {_cwd_placeholder}/.vscode/mcp.json\n"
        f"               --global:  {_global_target_path('vscode')}\n"
        f"  cursor       per-repo:  {_cwd_placeholder}/.cursor/mcp.json\n"
        f"               --global:  {_global_target_path('cursor')}\n"
        f"  claude-code  per-repo:  {_cwd_placeholder}/.mcp.json\n"
        f"               --global:  {_global_target_path('claude-code')}\n"
        f"  antigravity  always:    {_global_target_path('antigravity')}  [--global has no effect]\n"
        f"  codex        always:    {_global_target_path('codex')}  [--global has no effect]\n"
        "  all          all targets above (default)\n"
        "\n"
        "Agent instructions and IDE onboarding snippets are available at\n"
        "/dashboard/instruction in the Minder dashboard — no CLI install needed.\n"
    )

    install = subparsers.add_parser(
        "install",
        help="Install Minder MCP server config into IDE config files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_mcp_epilog,
    )
    install.add_argument("--target", action="append", metavar="TARGET", help="Target IDE (see list below).")
    install.add_argument("--global", dest="global_install", action="store_true", help="Write to IDE global config instead of per-repo file.")
    install.add_argument("--cwd", default=".", help="Workspace directory (for per-repo targets).")
    install.add_argument("--config-path", default=str(client_config_path()), help="Path to client config.")
    install.set_defaults(func=install_mcp_command)

    uninstall = subparsers.add_parser(
        "uninstall",
        help="Remove Minder MCP server config from IDE config files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_mcp_epilog,
    )
    uninstall.add_argument("--target", action="append", metavar="TARGET", help="Target IDE (see list below).")
    uninstall.add_argument("--global", dest="global_install", action="store_true", help="Remove from IDE global config instead of per-repo file.")
    uninstall.add_argument("--cwd", default=".", help="Workspace directory (for per-repo targets).")
    uninstall.set_defaults(func=uninstall_mcp_command)

    remove = subparsers.add_parser(
        "remove",
        help="Remove Minder MCP server config (alias for uninstall).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_mcp_epilog,
    )
    remove.add_argument("--target", action="append", metavar="TARGET", help="Target IDE (see list below).")
    remove.add_argument("--global", dest="global_install", action="store_true", help="Remove from IDE global config instead of per-repo file.")
    remove.add_argument("--cwd", default=".", help="Workspace directory (for per-repo targets).")
    remove.set_defaults(func=remove_mcp_command)

    # ── Sync ──────────────────────────────────────────────────────────────────
    sync = subparsers.add_parser("sync", help="Sync repository state with Minder server.")
    sync.add_argument("--repo-id", help="Repository UUID.")
    sync.add_argument("--repo-path", default=".", help="Path to sync.")
    sync.add_argument("--diff-base", help="Git base ref for delta.")
    sync.add_argument("--dry-run", action="store_true", help="Preview payload without sending.")
    sync.add_argument("--skip-upgrade-check", action="store_true", help="Skip CLI version check.")
    sync.add_argument("--config-path", default=str(client_config_path()), help="Path to client config.")
    sync.set_defaults(func=sync_command)

    # ── Updates ───────────────────────────────────────────────────────────────
    update = subparsers.add_parser("update", help="Check for or apply CLI and server updates.")
    update.add_argument("--check", action="store_true", help="Only check — do not apply.")
    update.add_argument("--component", choices=("cli", "server", "all"), default="cli")
    update.add_argument("--manager", choices=("auto", "uv", "pipx", "pip"), default="auto")
    update.add_argument("--install-dir", help="Deployment directory for server updates.")
    update.set_defaults(func=lambda args: check_update_command(args) if args.check else update_command(args))

    check_update = subparsers.add_parser("check-update", help="Check for available updates without applying them.")
    check_update.add_argument("--component", choices=("cli", "server", "all"), default="all")
    check_update.add_argument("--install-dir", help="Deployment directory for server check.")
    check_update.set_defaults(func=check_update_command)

    version = subparsers.add_parser("version", help="Show version information.")
    version.add_argument("--check", action="store_true", help="Check for newer version on PyPI.")
    version.set_defaults(func=version_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if hasattr(args, "func"):
        return args.func(args)

    return 0
