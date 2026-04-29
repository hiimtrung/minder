from __future__ import annotations

import argparse

from .utils.version import installed_package_version
from .utils.common import client_config_path
from .commands.auth import login_command
from .commands.mcp import install_mcp_command, uninstall_mcp_command, remove_mcp_command, _global_target_path
from .commands.ide import install_ide_command, uninstall_ide_command
from .commands.agent import install_agent_command, uninstall_agent_command, remove_agent_command
from .commands.update import version_command, check_update_command, update_command
from .commands.sync import sync_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minder",
        description="Minder CLI - Agentic Development Infrastructure",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # Global version flag
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"minder {installed_package_version() or 'dev'}",
    )
    
    subparsers = parser.add_subparsers(dest="command", title="commands", metavar="<command>")
    
    # --- Auth ---
    login = subparsers.add_parser("login", help="Authenticate with Minder server.")
    login.add_argument("--client-key", help="Client API key (mkc_...).")
    login.add_argument("--protocol", choices=("sse", "stdio"), help="Transport protocol.")
    login.add_argument("--server-url", help="Minder server URL.")
    login.add_argument("--config-path", default=str(client_config_path()), help="Path to save config.")
    login.set_defaults(func=login_command)
    
    # --- IDE / MCP ---
    install = subparsers.add_parser("install", help="Install Minder integration (MCP/IDE).")
    install_subs = install.add_subparsers(dest="subcommand", required=True)
    
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
    )

    mcp_in = install_subs.add_parser(
        "mcp",
        help="Install MCP server config.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_mcp_epilog,
    )
    mcp_in.add_argument("--target", action="append", metavar="TARGET", help="Target to install (see targets below).")
    mcp_in.add_argument("--global", dest="global_install", action="store_true", help="Write to the IDE's global config instead of the repo-local file.")
    mcp_in.add_argument("--cwd", default=".", help="Workspace directory (used for per-repo targets).")
    mcp_in.add_argument("--config-path", default=str(client_config_path()), help="Path to client config.")
    mcp_in.set_defaults(func=install_mcp_command)
    
    ide_in = install_subs.add_parser("ide", help="Install full IDE bootstrap (MCP + Assets).")
    ide_in.add_argument("--target", action="append", help="Target IDE.")
    ide_in.add_argument("--cwd", default=".", help="Workspace directory.")
    ide_in.add_argument("--config-path", default=str(client_config_path()), help="Path to client config.")
    ide_in.set_defaults(func=install_ide_command)
    
    _agent_epilog = """\
targets (scope):
  vscode       ~/.copilot/agents/minder.agent.md               [global – all repos]
  claude-code  ~/.claude/agents/minder.md                      [global – all repos]
  codex        ~/.codex/AGENTS.md                              [global – all repos]
  antigravity  ~/.gemini/GEMINI.md                             [global – all repos]
  cursor       <repo>/.cursor/rules/minder.mdc                 [per-repo]
  all          all targets above (default)
"""
    agent_in = install_subs.add_parser(
        "agent",
        help="Install Minder Agent rules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_agent_epilog,
    )
    agent_in.add_argument("--target", action="append", metavar="TARGET", help="Target to install (see targets below).")
    agent_in.add_argument("--cwd", default=".", help="Workspace directory (used for per-repo targets).")
    agent_in.set_defaults(func=install_agent_command)
    
    uninstall = subparsers.add_parser("uninstall", help="Remove Minder integration.")
    uninstall_subs = uninstall.add_subparsers(dest="subcommand", required=True)
    
    mcp_un = uninstall_subs.add_parser(
        "mcp",
        help="Remove MCP server config.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_mcp_epilog,
    )
    mcp_un.add_argument("--target", action="append", metavar="TARGET", help="Target to remove (see targets below).")
    mcp_un.add_argument("--global", dest="global_install", action="store_true", help="Remove from the IDE's global config instead of the repo-local file.")
    mcp_un.add_argument("--cwd", default=".", help="Workspace directory (used for per-repo targets).")
    mcp_un.set_defaults(func=uninstall_mcp_command)
    
    ide_un = uninstall_subs.add_parser("ide", help="Remove IDE bootstrap assets.")
    ide_un.add_argument("--target", action="append", help="Target IDE.")
    ide_un.add_argument("--cwd", default=".", help="Workspace directory.")
    ide_un.set_defaults(func=uninstall_ide_command)
    
    agent_un = uninstall_subs.add_parser(
        "agent",
        help="Remove Minder Agent rules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_agent_epilog,
    )
    agent_un.add_argument("--target", action="append", metavar="TARGET", help="Target to remove (see targets below).")
    agent_un.add_argument("--cwd", default=".", help="Workspace directory (used for per-repo targets).")
    agent_un.set_defaults(func=uninstall_agent_command)
    
    # --- Remove (alias for uninstall) ---
    remove = subparsers.add_parser("remove", help="Remove Minder integration (alias for uninstall).")
    remove_subs = remove.add_subparsers(dest="subcommand", required=True)

    remove_mcp = remove_subs.add_parser(
        "mcp",
        help="Remove MCP server config.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_mcp_epilog,
    )
    remove_mcp.add_argument("--target", action="append", metavar="TARGET", help="Target to remove (see targets below).")
    remove_mcp.add_argument("--global", dest="global_install", action="store_true", help="Remove from the IDE's global config instead of the repo-local file.")
    remove_mcp.add_argument("--cwd", default=".", help="Workspace directory (used for per-repo targets).")
    remove_mcp.set_defaults(func=remove_mcp_command)

    remove_agent = remove_subs.add_parser(
        "agent",
        help="Remove Minder Agent rules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_agent_epilog,
    )
    remove_agent.add_argument("--target", action="append", metavar="TARGET", help="Target to remove (see targets below).")
    remove_agent.add_argument("--cwd", default=".", help="Workspace directory (used for per-repo targets).")
    remove_agent.set_defaults(func=remove_agent_command)

    # --- Sync ---
    sync = subparsers.add_parser("sync", help="Sync repository state with Minder server.")
    sync.add_argument("--repo-id", help="Repository UUID.")
    sync.add_argument("--repo-path", default=".", help="Path to sync.")
    sync.add_argument("--diff-base", help="Git base ref for delta.")
    sync.add_argument("--dry-run", action="store_true", help="Preview payload.")
    sync.add_argument("--skip-upgrade-check", action="store_true", help="Don't check for CLI updates.")
    sync.add_argument("--config-path", default=str(client_config_path()), help="Path to client config.")
    sync.set_defaults(func=sync_command)
    
    # --- Maintenance ---
    update = subparsers.add_parser("update", help="Check for or apply updates.")
    update.add_argument("--check", action="store_true", help="Only check for updates, don't apply.")
    update.add_argument("--component", choices=("cli", "server", "all"), default="cli")
    update.add_argument("--manager", choices=("auto", "uv", "pipx", "pip"), default="auto")
    update.add_argument("--install-dir", help="Installation directory for server updates.")
    update.set_defaults(func=lambda args: check_update_command(args) if args.check else update_command(args))
    
    # --- Version ---
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
