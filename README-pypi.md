# minder-cli

[![PyPI version](https://img.shields.io/pypi/v/minder-cli.svg)](https://pypi.org/project/minder-cli/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**minder-cli** is the command-line interface for [Minder](https://github.com/hiimtrung/minder) — a self-hosted MCP platform for repository-aware engineering intelligence.

The CLI handles repository sync, MCP config installation, authentication, and self-updates. It connects to a **Minder Server** which runs the MCP gateway, RAG pipeline, memory engine, and admin dashboard.

## Installation

```bash
# Recommended
uv tool install minder-cli

# Alternative
pipx install minder-cli
```

## Requirements

A running [Minder Server](https://github.com/hiimtrung/minder) — see the [server setup guide](https://github.com/hiimtrung/minder/blob/main/docs/guides/local-setup.md) to get one running with Docker.

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

## MCP Tools (once connected)

| Tool | Description |
|------|-------------|
| `minder_query` | Full RAG pipeline: retrieve → reason → verify → respond |
| `minder_search_code` | Semantic code search across indexed repositories |
| `minder_search_errors` | Look up past error patterns |
| `minder_find_impact` | Find what a change might affect |
| `minder_memory_store` / `minder_memory_recall` | Persistent engineering memory |
| `minder_session_create` / `minder_session_save` / `minder_session_restore` | Cross-machine session continuity |
| `minder_workflow_get` / `minder_workflow_guard` | Workflow governance |

## Links

- [GitHub Repository](https://github.com/hiimtrung/minder)
- [Server Setup Guide](https://github.com/hiimtrung/minder/blob/main/docs/guides/local-setup.md)
- [Admin & Client Onboarding](https://github.com/hiimtrung/minder/blob/main/docs/guides/admin-client-onboarding.md)
- [System Design](https://github.com/hiimtrung/minder/blob/main/docs/architecture/system-design.md)

## License

Apache License 2.0. See [LICENSE](https://github.com/hiimtrung/minder/blob/main/LICENSE) for details.
