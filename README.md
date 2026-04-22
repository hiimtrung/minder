# Minder

[![PyPI version](https://img.shields.io/pypi/v/minder-cli.svg)](https://pypi.org/project/minder-cli/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**Minder** is a self-hosted MCP (Model Context Protocol) platform for repository-aware engineering intelligence.

It combines a local-first inference stack, a persistent memory and workflow engine, and a developer-facing CLI into a single deployable unit.

## What's in this repo

| Component | Description |
|-----------|-------------|
| **Minder Server** | MCP gateway — SSE + stdio transport, RAG pipeline, workflow engine, memory, admin HTTP |
| **Minder CLI** (`minder-cli` on PyPI) | Edge CLI — IDE scaffold, repo sync, login, self-update |
| **Minder Dashboard** | Astro admin console — client management, onboarding, skill catalog |

## Architecture

```
Developer → minder-cli → Minder Server ←→ AI agents (Codex / Copilot / Claude)
                              │
               ┌──────────────┼──────────────┐
               │              │              │
           MongoDB          Redis         Milvus
         (graph/memory)   (cache)      (vector search)
               │
         ┌─────┴──────┐
         │            │
      LiteRT-LM   Ollama (Docker)
      (LLM gen)   (embedding)
```

- **LLM inference**: LiteRT-LM (Google AI Edge) — on-device, hardware-accelerated, no HTTP overhead
- **Embedding inference**: Ollama running as a Docker container (`ollama/ollama:latest`) — isolated, auto-managed

## Quick Start

### Run the server

```bash
# 1. Download the LiteRT-LM model
./scripts/download_models.sh

# 2. Start infra (Ollama + MongoDB + Redis + Milvus)
docker compose -f docker/docker-compose.local.yml up -d

# 3. Run Minder Server
uv run python -m minder.server
```

Or use the one-command release installer (Docker only, no local uv needed):

```bash
curl -fsSL https://raw.githubusercontent.com/hiimtrung/minder/main/scripts/release/install-minder-release.sh | bash
```

### Connect the CLI

```bash
# Install
uv tool install minder-cli

# Log in with your client key
minder login --client-key mkc_your_key --server-url http://localhost:8800/sse

# Set up IDE integration (VS Code, Cursor, Claude Code)
minder install-ide --target vscode --target claude-code

# Sync a repository
minder sync --repo-id <uuid>
```

## MCP Tools

When connected, Minder exposes these tools to your AI agents:

| Tool | Description |
|------|-------------|
| `minder_query` | Full RAG pipeline: retrieve → reason → verify → respond |
| `minder_search_code` | Semantic code search across indexed repos |
| `minder_memory_recall` | Retrieve persisted engineering memory |
| `minder_workflow_get` | Read current workflow state |
| `minder_session_restore` | Restore session continuity across context windows |

## Documentation

- [System Design](docs/system-design.md)
- [Server Setup](docs/minder-server.md)
- [Local Dev Setup](docs/guides/local-setup.md)
- [Production Deployment](docs/guides/production-deployment.md)
- [Admin & Client Onboarding](docs/guides/admin-client-onboarding.md)

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
