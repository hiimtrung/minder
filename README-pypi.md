# minder-cli

[![PyPI version](https://img.shields.io/pypi/v/minder-cli.svg)](https://pypi.org/project/minder-cli/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**minder-cli** is the command-line interface for [Minder](https://github.com/hiimtrung/minder) — a self-hosted MCP platform for repository-aware engineering intelligence.

The CLI handles repository sync, MCP config installation, authentication, and self-updates. It connects to a **Minder Server** which runs the MCP gateway, RAG pipeline, memory engine, workflow engine, and admin dashboard.

## Installation

```bash
# Recommended
uv tool install minder-cli

# Alternative
pipx install minder-cli
```

## Requirements

A running [Minder Server](https://github.com/hiimtrung/minder) — see the [server setup guide](https://github.com/hiimtrung/minder/blob/main/docs/guides/local-setup.md) to get one running natively (no Docker required).

## Quick Start

### 1. Authenticate

```bash
minder login --client-key mkc_your_client_key --server-url http://localhost:8800/sse
```

Create a client and get your `mkc_...` key from the dashboard at `/dashboard/clients`.

### 2. Write MCP config to your IDE (optional)

```bash
minder install --target vscode --target claude-code
```

MCP snippets and agent instructions are also available from the Minder dashboard at `/dashboard/clients` and `/dashboard/instruction` — no CLI install required.

### 3. Sync a repository

```bash
minder sync
```

Indexes code and documentation so AI agents can use semantic search and knowledge-graph tools.

## Commands

| Command | Description |
|---------|-------------|
| `minder login` | Authenticate the CLI against a Minder Server |
| `minder install` | Write MCP server config into IDE config files |
| `minder uninstall` | Remove MCP server config from IDE config files |
| `minder sync` | Index a repository into the Minder Server |
| `minder update` | Update CLI or server in place |
| `minder check-update` | Check for available CLI and server updates |
| `minder version` | Show version information |

## MCP Tools (26 tools)

Once connected, Minder exposes these tools to your AI agents:

| Group | Tools | Description |
|-------|-------|-------------|
| **Auth** | `minder_auth_login`, `minder_auth_exchange_client_key`, `minder_auth_whoami` | Authentication and identity |
| **Session** | `minder_session_boot`, `minder_session_save`, `minder_session_list`, `minder_session_summarize`, `minder_session_cleanup` | Cross-machine context continuity |
| **Memory** | `minder_memory_store`, `minder_memory_recall`, `minder_memory_list`, `minder_memory_delete` | Persistent project facts and decisions |
| **Skills** | `minder_skill_store`, `minder_skill_recall`, `minder_skill_list`, `minder_skill_delete` | Reusable workflow patterns |
| **Workflow** | `minder_workflow_step`, `minder_workflow_update`, `minder_workflow_guard` | Workflow governance and step enforcement |
| **Search** | `minder_search_code`, `minder_search_errors`, `minder_search_graph`, `minder_find_impact` | Code and graph intelligence |
| **Agents** | `minder_agent_list`, `minder_agent_get`, `minder_agent_store` | SubAgent registry |

`minder_session_boot` is the single session entry point — it creates, finds, or restores a session transparently. Pass `session_id` to restore by UUID; pass `project_name` alone to find or create.

## Links

- [GitHub Repository](https://github.com/hiimtrung/minder)
- [Server Setup Guide](https://github.com/hiimtrung/minder/blob/main/docs/guides/local-setup.md)
- [Admin & Client Onboarding](https://github.com/hiimtrung/minder/blob/main/docs/guides/admin-client-onboarding.md)
- [MCP Tool Reference](https://github.com/hiimtrung/minder/blob/main/docs/roadmap/03-data-model-and-tools.md)
- [System Design](https://github.com/hiimtrung/minder/blob/main/docs/architecture/system-design.md)

## License

Apache License 2.0. See [LICENSE](https://github.com/hiimtrung/minder/blob/main/LICENSE) for details.
