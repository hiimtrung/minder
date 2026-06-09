# Minder

[![PyPI version](https://img.shields.io/pypi/v/minder-cli.svg)](https://pypi.org/project/minder-cli/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**Minder** is a self-hosted MCP (Model Context Protocol) platform for repository-aware engineering intelligence.

It runs **natively** on macOS, Linux, and Windows — no Docker, no external services. The stack is a Python FastAPI server with SQLite, Turbovec (embedded vector search), and llama-cpp-python for local LLM inference, distributed as a Tauri desktop app or standalone server.

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
               SQLite    Turbovec           llama-cpp-python
          (users, sessions,  (embedded vector    (LLM, GGUF,
           workflows, graph)  search, .tvim file)  Metal/CPU)
```

- **Transport**: SSE (`/sse`), streamable HTTP (`/mcp`), stdio
- **LLM inference**: llama-cpp-python with GGUF models auto-downloaded from HuggingFace (Metal on Mac, CPU elsewhere)
- **Vector search**: Turbovec — embedded, file-based 4-bit quantized ANN index, no separate server
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

## MCP Tools (26 tools)

Minder exposes a lean set of 26 tools organized into 7 groups. All session tools are always available; other tools require explicit `tool_scopes` on the client.

### Auth

| Tool | Description |
|------|-------------|
| `minder_auth_login` | Exchange an admin API key for a JWT bearer token |
| `minder_auth_exchange_client_key` | Exchange a `mkc_...` client key for a scoped access token |
| `minder_auth_whoami` | Return the current principal identity and active scopes |

### Session (always available)

`minder_session_boot` is the single entry point for every session flow — it creates, finds, or restores a session in one call.

| Tool | Description |
|------|-------------|
| `minder_session_boot` | Create or recover a named session; pass `session_id` to restore by UUID |
| `minder_session_list` | List sessions owned by the calling principal, newest first |
| `minder_session_save` | Checkpoint state; pass `branch` and `open_files` to update context in one call |
| `minder_session_summarize` | Generate a structured summary before `/compact` or long interruptions |
| `minder_session_cleanup` | Delete expired sessions and their history |

### Memory

| Tool | Description |
|------|-------------|
| `minder_memory_store` | Store a project fact or decision; pass `memory_id` to update an existing entry |
| `minder_memory_recall` | Retrieve memories by semantic similarity, optionally filtered by workflow step |
| `minder_memory_list` | List all memories for the current principal |
| `minder_memory_delete` | Delete a memory entry by ID |

### Skills

| Tool | Description |
|------|-------------|
| `minder_skill_store` | Store a reusable pattern; pass `skill_id` to update, `deprecated=True` to retire |
| `minder_skill_recall` | Retrieve skills compatible with the current workflow step |
| `minder_skill_list` | List skills by step, tags, or quality score |
| `minder_skill_delete` | Remove a skill by ID |

### Workflow

| Tool | Description |
|------|-------------|
| `minder_workflow_step` | Return current step and instruction envelope; pass `include_definition=true` for full workflow definition |
| `minder_workflow_update` | Mark a step complete or attach an artifact |
| `minder_workflow_guard` | Validate whether an action is allowed in the current step |

### Search & Graph

| Tool | Description |
|------|-------------|
| `minder_search_code` | Semantic code search across indexed repositories |
| `minder_search_errors` | Look up past error patterns and resolutions |
| `minder_search_graph` | Structural graph queries: routes, imports, dependencies |
| `minder_find_impact` | Find what a change to a symbol, file, or route might affect |

### Agents

| Tool | Description |
|------|-------------|
| `minder_agent_list` | List available subagents, optionally filtered by workflow step |
| `minder_agent_get` | Load a subagent's system prompt and tool list |
| `minder_agent_store` | Create or update a subagent definition |

## Session Continuity

`minder_session_boot` is the single session entry point for all agents. It handles create, find, and restore transparently:

```
# First run on a project — creates a new session
minder_session_boot(project_name="my-api", project_context={"repo_path": "/dev/my-api"})
→ { session_id: "a1b2...", session_found: false }

# After /compact or machine switch — recovers by name
minder_session_boot(project_name="my-api")
→ { session_id: "a1b2...", session_found: true, session_summary: {...}, _next_steps: [...] }

# Checkpoint work and update branch context in one call
minder_session_save(
  session_id="a1b2...",
  state={"task": "...", "next_steps": [...]},
  branch="feat/my-feature",
  open_files=["src/service.py"]
)
```

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
- [MCP Tool Reference](docs/roadmap/03-data-model-and-tools.md)

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
