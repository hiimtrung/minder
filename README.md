# Minder

[![PyPI version](https://img.shields.io/pypi/v/minder-cli.svg)](https://pypi.org/project/minder-cli/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**Minder** is a self-hosted MCP (Model Context Protocol) platform for repository-aware engineering intelligence.

It combines an LLM inference stack, a persistent memory and workflow engine, a browser admin console, and a lightweight CLI into a single deployable unit.

## What's in this repo

| Component | Description |
|-----------|-------------|
| **Minder Server** | MCP gateway — SSE + streamable HTTP + stdio, RAG pipeline, workflow engine, memory, admin HTTP |
| **Minder Dashboard** | Astro admin console — client management, onboarding snippets, agent instructions, skill catalog, chat |
| **Minder CLI** (`minder-cli` on PyPI) | Edge CLI — repo sync, MCP config install, login, self-update |

## Architecture

```
Developer workstation
  ├── minder-cli          repo sync, MCP config
  └── AI agent (IDE)  ──► Minder Server :8800
                              │
                    ┌─────────┼──────────┐
                    │         │          │
                Qdrant     SQLite     llama-cpp-python
              (vectors)   (graph/    (LLM + embedding,
                           memory)    GGUF on host)
```

- **Transport**: SSE (`/sse`), streamable HTTP (`/mcp`), stdio
- **LLM inference**: llama-cpp-python with GGUF models auto-downloaded from HuggingFace (Metal on Mac, CPU elsewhere)
- **Vector search**: Qdrant for semantic retrieval
- **Operational storage**: SQLite for graph, memory, sessions, and audit

## Quick Start

### 1. Run the server

```bash
# Start infra (Qdrant)
docker compose -f docker/docker-compose.local.yml up -d

# Run Minder Server (GGUF models auto-download on first start)
uv run python scripts/dev_server.py
```

Or use the one-command release installer (Docker only):

```bash
curl -fsSL https://raw.githubusercontent.com/hiimtrung/minder/main/scripts/release/install-minder-release.sh | bash
```

### 2. Open the dashboard

```
http://localhost:8800/dashboard
```

First run → `/dashboard/setup` to create an admin and get your `mk_...` key.

### 3. Create a client and connect your IDE

1. Open `/dashboard/clients` → create a client → save the `mkc_...` key (shown once in a modal)
2. Open the client detail → copy the MCP snippet for your IDE from **Copy-ready MCP snippets**
3. Open `/dashboard/instruction` → copy the agent orchestration rules for your IDE

### 4. Install the CLI and sync a repository

```bash
# Install
uv tool install minder-cli

# Log in
minder login --client-key mkc_your_key --server-url http://localhost:8800/sse

# Write MCP config to your IDE (optional — dashboard shows it too)
minder install --target vscode --target claude-code

# Sync a repository
minder sync
```

## MCP Tools

When connected, Minder exposes these tools to your AI agents:

| Tool | Description |
|------|-------------|
| `minder_query` | Full RAG pipeline: retrieve → reason → verify → respond |
| `minder_search_code` | Semantic code search across indexed repos |
| `minder_search_errors` | Look up past error patterns |
| `minder_find_impact` | Find what a change might affect |
| `minder_memory_store` / `minder_memory_recall` | Persistent engineering memory |
| `minder_session_create` / `minder_session_save` / `minder_session_restore` | Cross-machine session continuity |
| `minder_workflow_get` / `minder_workflow_step` / `minder_workflow_guard` | Workflow governance |
| `minder_skill_store` / `minder_skill_recall` | Reusable pattern catalog |
| `minder_agent_list` / `minder_agent_get` | SubAgent registry |

## Dashboard Pages

| Route | Description |
|-------|-------------|
| `/dashboard` | Home — stats and quick nav |
| `/dashboard/clients` | Create clients, copy MCP snippets |
| `/dashboard/instruction` | Agent orchestration rules — copy for Claude Code, Cursor, VS Code, Gemini, Codex |
| `/dashboard/sessions` | LLM session management |
| `/dashboard/memories` | Persistent memory browser |
| `/dashboard/skills` | Skill / pattern catalog |
| `/dashboard/agents` | SubAgent registry |
| `/dashboard/chat` | Browser-based runtime chat |
| `/dashboard/repositories` | Repo graph explorer |
| `/dashboard/workflows` | Workflow definitions |
| `/dashboard/observability` | Audit and trace |

## Documentation

- [System Design](docs/architecture/system-design.md)
- [Local Dev Setup](docs/guides/local-setup.md)
- [Production Deployment](docs/guides/production-deployment.md)
- [Admin & Client Onboarding](docs/guides/admin-client-onboarding.md)
- [Minder CLI](docs/guides/minder-cli.md)

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
