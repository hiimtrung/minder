# Admin and Client Onboarding Guide

This guide covers the full onboarding flow for Minder running natively or as a headless server.

Related references:
- [System Design](../architecture/system-design.md)
- [MCP Tool Reference](../roadmap/03-data-model-and-tools.md)

---

## 1. Create the admin user

If this is a fresh deployment, open:

- [http://localhost:8800/dashboard/setup](http://localhost:8800/dashboard/setup)

Complete the setup form and save the returned admin API key (`mk_...`). This is shown exactly once.

If the admin API key is lost later, recover it with:

```bash
PYTHONPATH=src UV_CACHE_DIR=.uv-cache uv run python scripts/reset_admin_api_key.py --username admin
```

## 2. Sign into the browser dashboard

Open:

- [http://localhost:8800/dashboard/login](http://localhost:8800/dashboard/login)

Enter the admin API key. The browser is redirected to `/dashboard` and a session cookie is set.

For API clients (`curl`, Postman), use a bearer token:

```bash
# Via minder_auth_login MCP tool or:
curl -X POST http://localhost:8800/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"api_key": "mk_..."}'
```

## 3. Create an MCP client

Open `/dashboard/clients` → **Create Client**. Fill in:

- **name** — human-readable label
- **slug** — stable URL-safe identifier (e.g. `my-ide-codex`)
- **description** — optional
- **tool scopes** — select from the multi-select, or use a preset (see below)
- **repo scopes** — `*` for all repos, or specific repo paths

Use the preset buttons to prefill tool scopes:
- **Query Only** — search and RAG tools only
- **Read Only** — search + memory recall + workflow read
- **Full Dev** — all tools needed for active development work

After submission, the `mkc_...` client API key is shown **exactly once**. Save it.

Via the admin API:

```bash
curl -X POST http://localhost:8800/v1/admin/clients \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Claude Code Local",
    "slug": "claude-code-local",
    "tool_scopes": [
      "minder_memory_store", "minder_memory_recall", "minder_memory_list",
      "minder_skill_store", "minder_skill_recall", "minder_skill_list",
      "minder_workflow_step", "minder_workflow_update", "minder_workflow_guard",
      "minder_search_code", "minder_search_errors", "minder_search_graph",
      "minder_find_impact", "minder_agent_list", "minder_agent_get"
    ],
    "repo_scopes": ["*"]
  }'
```

## 4. Choose a client auth mode

### Option A: Direct client key auth (recommended)

Pass the `mkc_...` key directly:

| Transport | How to pass |
|-----------|-------------|
| SSE / HTTP | `X-Minder-Client-Key: mkc_...` header |
| stdio | `MINDER_CLIENT_API_KEY=mkc_...` env var |

### Option B: Token exchange

Exchange the client key for a short-lived bearer token:

```bash
curl -X POST http://localhost:8800/v1/auth/token-exchange \
  -H "Content-Type: application/json" \
  -d '{"client_api_key": "mkc_..."}'
```

Returns:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in": 3600,
  "client": { "slug": "claude-code-local" }
}
```

## 5. Connect your IDE

All snippets are also available in the dashboard at `/dashboard/clients` → client detail → **Copy-ready MCP snippets**.

### Claude Code

```json
{
  "mcpServers": {
    "minder": {
      "type": "sse",
      "url": "http://localhost:8800/sse",
      "headers": { "X-Minder-Client-Key": "mkc_..." }
    }
  }
}
```

Place in `~/.claude/mcp.json` (global) or `.mcp.json` (project root).

Optional stdio fallback:

```bash
export MINDER_CLIENT_API_KEY="mkc_..."
MINDER_SERVER__TRANSPORT=stdio uv run python -m minder.server
```

### VS Code / GitHub Copilot

```json
{
  "servers": {
    "minder": {
      "type": "sse",
      "url": "http://localhost:8800/sse",
      "headers": { "X-Minder-Client-Key": "mkc_..." }
    }
  }
}
```

Place in `.vscode/mcp.json` (workspace) or `~/Library/Application Support/Code/User/mcp.json` (global on macOS).

### Cursor

```json
{
  "mcpServers": {
    "minder": {
      "url": "http://localhost:8800/mcp",
      "headers": { "X-Minder-Client-Key": "mkc_..." }
    }
  }
}
```

Place in `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global).

### Codex

```toml
[mcp_servers.minder]
url = "http://localhost:8800/sse"
http_headers = { "X-Minder-Client-Key" = "mkc_..." }
```

### Google Antigravity

```json
{
  "mcpServers": {
    "minder": {
      "serverUrl": "http://localhost:8800/mcp",
      "headers": { "X-Minder-Client-Key": "mkc_..." }
    }
  }
}
```

## 6. Copy agent orchestration rules

Open `/dashboard/instruction` to get the full Minder Agent Orchestration Rules prompt for your IDE:

| IDE | Target file |
|-----|------------|
| Claude Code | `~/.claude/agents/minder.md` |
| Cursor | `.cursor/rules/minder.mdc` (per-repo) |
| VS Code / Copilot | `~/.copilot/agents/minder.agent.md` |
| Google Antigravity | `~/.gemini/GEMINI.md` |
| Codex | `~/.codex/AGENTS.md` |

Each card shows the exact content to paste and a one-click copy button.

## 7. Install the CLI and sync a repository

```bash
uv tool install minder-cli

# Log in
minder login --client-key mkc_your_key --server-url http://localhost:8800/sse

# Optional: write MCP config to your IDE
minder install --target claude-code --target vscode

# Sync your repo
cd /path/to/your/repo
minder sync
```

After `minder sync`, the repo appears in `/dashboard/repositories` and agents can search it.

---

## 8. Session Continuity — How It Works

Minder sessions are the server-side checkpoint for LLM work context. Because sessions are stored server-side, the same agent can resume exactly where it left off from **any machine** using the same client API key.

### `minder_session_boot` — single entry point

`minder_session_boot` handles **create, find, and restore** in one call:

```
# First run — creates session and returns session_found=false
minder_session_boot(
  project_name = "my-api--claude",          ← stable slug: "<repo>--<client>"
  project_context = {"repo_path": "/dev/my-api", "repo_id": "<uuid>"}
)
→ { session_id: "a1b2...", session_found: false, _next_steps: [...] }

# After /compact or machine switch — finds session and returns session_found=true
minder_session_boot(project_name="my-api--claude")
→ {
    session_id: "a1b2...",
    session_found: true,
    session_summary: { problem_framing: {...}, next_valid_actions: [...] },
    _next_steps: [...]
  }

# Restore specific session by UUID (from .minder/agent.json)
minder_session_boot(project_name="my-api--claude", session_id="a1b2c3d4-...")
```

### Checkpoint with context

`minder_session_save` now handles both state checkpointing and context updates in one call:

```
minder_session_save(
  session_id = "a1b2...",
  state = {
    "task": "Implement data pipeline",
    "completed": ["schema design"],
    "next_steps": ["write tests", "implement service"],
    "key_decisions": ["user_id nullable for client sessions"],
  },
  branch = "feat/data-pipeline",
  open_files = ["src/service.py", "src/models/session.py"]
)
```

### Session tool reference

| Tool | Always available | Description |
|------|:----------------:|-------------|
| `minder_session_boot` | ✅ | Create, find, or restore a session — single entry point |
| `minder_session_list` | ✅ | List all sessions for the calling principal |
| `minder_session_save` | ✅ | Checkpoint state and update branch/file context |
| `minder_session_summarize` | ✅ | Generate structured summary before `/compact` |
| `minder_session_cleanup` | ✅ | Delete expired sessions and history |

All session tools are **always available** — no `tool_scopes` grant is needed.

---

## 9. Memory vs Skills — What to store where

| Concern | Use | When |
|---------|-----|------|
| Project-specific facts | `minder_memory_store` | "We use JWT for auth in this project" |
| Architectural decisions | `minder_memory_store` | "user_id is nullable — supports client sessions" |
| Confirmed file paths / symbols | `minder_memory_store` | "auth middleware is in `src/auth/middleware.py`" |
| Reusable patterns | `minder_skill_store` | "How to write async SQLAlchemy migrations" |
| Step checklists | `minder_skill_store` | "TDD step: write failing test first" |
| Cross-project conventions | `minder_skill_store` | "Always use `uv` not `pip`" |

Both tools act as upsert when an ID is provided:

```
# Update existing memory
minder_memory_store(memory_id="uuid", title="Auth approach", content="Updated content")

# Retire a skill (hidden from recall but preserved in history)
minder_skill_store(skill_id="uuid", deprecated=True, ...)
```

---

## 10. Revoke a client key

Open the client detail page in `/dashboard/clients` and use the revoke action. After revocation:

- SSE direct auth with the old `mkc_...` key fails immediately
- stdio `MINDER_CLIENT_API_KEY` auth fails immediately
- existing short-lived tokens remain valid until they expire

---

## Recommended Operator Flow

1. Deploy the server (`make native-run` or `uv run python -m minder.server`).
2. Create the admin at `/dashboard/setup`.
3. Sign in at `/dashboard/login`.
4. Create one client per real MCP consumer from `/dashboard/clients`.
5. Scope each client to the smallest needed tool set.
6. Use direct client-key auth for local SSE and stdio integrations.
7. Copy onboarding snippets from the dashboard — do not handwrite MCP config.
8. Install the CLI (`uv tool install minder-cli`) and run `minder sync` for each repo.
9. Copy agent orchestration rules from `/dashboard/instruction` to your IDE.
10. Rotate or revoke client keys when a workstation or integration changes ownership.
