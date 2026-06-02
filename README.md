# Minder

[![PyPI version](https://img.shields.io/pypi/v/minder-cli.svg)](https://pypi.org/project/minder-cli/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**Minder** is a self-hosted MCP (Model Context Protocol) platform for repository-aware engineering intelligence.

It runs **natively** on macOS, Linux, and Windows — no Docker, no external services. The stack is a Python FastAPI server with SQLite, Milvus Lite (embedded vector search), and llama-cpp-python for local LLM inference, distributed as a Tauri desktop app or standalone server.

## What's in this repo

| Component                             | Description                                                                                           |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **Minder Server**                     | MCP gateway — SSE + streamable HTTP + stdio, RAG pipeline, workflow engine, memory, admin HTTP        |
| **Minder Dashboard**                  | Astro admin console — client management, onboarding snippets, agent instructions, skill catalog, chat |
| **Minder CLI** (`minder-cli` on PyPI) | Edge CLI — repo sync, MCP config install, login, self-update                                          |

## Architecture

```
Developer workstation
  ├── minder-cli          repo sync, MCP config
  └── AI agent (IDE)  ──► Minder Server :8800
                              │
                  ┌───────────┼───────────────────┐
                  │           │                   │
               SQLite    Milvus Lite        llama-cpp-python
          (users, sessions,  (embedded vector    (LLM, GGUF,
           workflows, graph)  search, file-based)  Metal/CPU)
```

- **Transport**: SSE (`/sse`), streamable HTTP (`/mcp`), stdio
- **LLM inference**: llama-cpp-python with GGUF models auto-downloaded from HuggingFace (Metal on Mac, CPU elsewhere)
- **Vector search**: Milvus Lite — embedded, file-based, no separate server
- **Relational storage**: SQLite (default) or PostgreSQL
- **Desktop**: optional Tauri v2 shell that bundles the Python server as a sidecar

## Quick Start

### 1. Install and run

To install the official desktop app release directly:
* **macOS / Linux**:
  ```bash
  curl -fsSL https://github.com/hiimtrung/minder/releases/latest/download/install-minder-release.sh | bash
  ```
* **Windows 10/11**:
  ```powershell
  iwr -useb https://github.com/hiimtrung/minder/releases/latest/download/install-minder-release.ps1 | iex
  ```

For local source development:
```bash
# Install dependencies and build the dashboard
make native-install

# Start the server (dashboard + MCP API on port 8800)
make native-run
```

GGUF models (`ggml-org/gemma-4-E2B-it-GGUF`) are downloaded automatically on first startup. No manual setup required.

### 2. Open the dashboard

```
http://localhost:8800/dashboard
```

First run → `/dashboard/setup` to create an admin and get your `mk_...` key.

### 3. Create a client and connect your IDE

1. Open `/dashboard/clients` → create a client → save the `mkc_...` key (shown once)
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

| Tool                                                                       | Description                                             |
| -------------------------------------------------------------------------- | ------------------------------------------------------- |
| `minder_query`                                                             | Full RAG pipeline: retrieve → reason → verify → respond |
| `minder_search_code`                                                       | Semantic code search across indexed repos               |
| `minder_search_errors`                                                     | Look up past error patterns                             |
| `minder_find_impact`                                                       | Find what a change might affect                         |
| `minder_memory_store` / `minder_memory_recall`                             | Persistent engineering memory                           |
| `minder_session_create` / `minder_session_save` / `minder_session_restore` | Cross-machine session continuity                        |
| `minder_workflow_get` / `minder_workflow_step` / `minder_workflow_guard`   | Workflow governance                                     |
| `minder_skill_store` / `minder_skill_recall`                               | Reusable pattern catalog                                |
| `minder_agent_list` / `minder_agent_get`                                   | SubAgent registry                                       |

## Dashboard Pages

| Route                      | Description                                                            |
| -------------------------- | ---------------------------------------------------------------------- |
| `/dashboard`               | Home — stats and quick nav                                             |
| `/dashboard/clients`       | Create clients, copy MCP snippets                                      |
| `/dashboard/instruction`   | Agent orchestration rules — copy for Claude Code, Cursor, VS Code      |
| `/dashboard/sessions`      | LLM session management                                                 |
| `/dashboard/memories`      | Persistent memory browser                                              |
| `/dashboard/skills`        | Skill / pattern catalog                                                |
| `/dashboard/agents`        | SubAgent registry                                                      |
| `/dashboard/chat`          | Browser-based runtime chat                                             |
| `/dashboard/repositories`  | Repo graph explorer                                                    |
| `/dashboard/workflows`     | Workflow definitions                                                   |
| `/dashboard/observability` | Audit and trace                                                        |

## Documentation

- [Local Dev Setup](docs/guides/local-setup.md)
- [Production Deployment](docs/guides/production-deployment.md)
- [System Design](docs/architecture/system-design.md)
- [Admin & Client Onboarding](docs/guides/admin-client-onboarding.md)
- [Minder CLI](docs/guides/minder-cli.md)

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
