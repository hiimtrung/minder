# minder-cli

[![PyPI version](https://img.shields.io/pypi/v/minder-cli.svg)](https://pypi.org/project/minder-cli/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**minder-cli** is the command-line interface for [Minder](https://github.com/hiimtrung/minder) — a self-hosted MCP platform for repository-aware engineering intelligence.

The CLI handles IDE scaffolding, repository sync, authentication, and self-updates. It connects to a **Minder Server** which runs the MCP gateway, RAG pipeline, memory engine, and admin console.

## Installation

```bash
# Recommended
uv tool install minder-cli

# Alternative
pipx install minder-cli
```

## Requirements

A running [Minder Server](https://github.com/hiimtrung/minder) — see the [server setup guide](https://github.com/hiimtrung/minder/blob/main/docs/minder-server.md) to get one running in minutes with Docker.

## Quick Start

### 1. Connect to your server

```bash
minder login --client-key mkc_your_client_key --server-url http://localhost:8800/sse
```

### 2. Set up IDE integration

```bash
# In your project root — scaffolds MCP config for your editor
minder install-ide --target vscode --target claude-code
```

Supported targets: `vscode`, `cursor`, `claude-code`.

### 3. Sync a repository

```bash
minder sync --repo-id <repository-uuid>
```

Indexes code and documentation so AI agents can use semantic search and RAG tools.

## Commands

| Command | Description |
|---------|-------------|
| `minder login` | Authenticate the CLI against a Minder Server |
| `minder install-ide` | Scaffold MCP assets for VS Code / Cursor / Claude Code |
| `minder sync` | Index a repository into the Minder Server |
| `minder check-update` | Check for available CLI and server updates |
| `minder self-update` | Update CLI or server in place |

## MCP Tools (once connected)

Your AI agents will have access to:

| Tool | Description |
|------|-------------|
| `minder_query` | Full RAG pipeline: retrieve → reason → verify → respond |
| `minder_search_code` | Semantic code search across indexed repositories |
| `minder_memory_recall` | Retrieve persisted engineering memory |
| `minder_workflow_get` | Read current workflow state |
| `minder_session_restore` | Restore session continuity across context windows |

## Links

- [GitHub Repository](https://github.com/hiimtrung/minder)
- [Server Setup Guide](https://github.com/hiimtrung/minder/blob/main/docs/minder-server.md)
- [Local Dev Setup](https://github.com/hiimtrung/minder/blob/main/docs/guides/local-setup.md)
- [System Design](https://github.com/hiimtrung/minder/blob/main/docs/system-design.md)

## License

Apache License 2.0. See [LICENSE](https://github.com/hiimtrung/minder/blob/main/LICENSE) for details.
