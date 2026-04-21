# Minder CLI

[![PyPI version](https://img.shields.io/pypi/v/minder-cli.svg)](https://pypi.org/project/minder-cli/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**Minder CLI** is the command-line interface for the Minder platform—a self-hosted MCP (Model Context Protocol) platform for repository-aware engineering intelligence.

## Features

- **IDE Integration**: Scaffold repository-local MCP assets for VS Code, Cursor, and Claude Code.
- **Repository Sync**: Auto-detect cross-repo dependencies and synchronize project knowledge.
- **Self-Management**: Check for updates and upgrade both CLI and Server components in place.
- **Unified Auth**: Simple login flow to connect your local development environment to your Minder Server.

## Installation

Install the CLI from PyPI using `uv` (recommended) or `pipx`:

```bash
uv tool install minder-cli
# or
pipx install minder-cli
```

## Quick Start

### 1. Connect to your Minder Server

Once you have a [Minder Server](docs/minder-server.md) running, log in with your client key:

```bash
minder login --client-key mkc_your_client_key --server-url http://localhost:8800/sse
```

### 2. Prepare your IDE

Set up MCP tools and instructions for your favorite editor:

```bash
# In your project root
minder install-ide --target vscode --target claude-code
```

### 3. Sync Repository

Index your code and documentation to enable semantic search and RAG tools:

```bash
minder sync --repo-id <repository-uuid>
```

## Available Tool Surface

When connected, Minder provides powerful tools to your AI agents:

| Tool | Description |
| --- | --- |
| `minder_query` | End-to-end RAG pipeline: retrieve + reason + verify |
| `minder_search_code` | Semantic code retrieval across indexed repositories |
| `minder_memory_recall` | Retrieve persisted memory entries |
| `minder_workflow_get` | Read current workflow state |

## Maintenance

Keep your tools up to date:

```bash
minder check-update
minder self-update --component cli
minder self-update --component server
```

## Related Links

- [Minder Server Setup](docs/minder-server.md)
- [Admin & Client Onboarding](docs/guides/admin-client-onboarding.md)
- [Local Setup Guide](docs/guides/local-setup.md)
- [System Architecture](docs/system-design.md)

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
