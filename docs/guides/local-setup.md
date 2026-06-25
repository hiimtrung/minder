# Local Development Guide

Minder runs **natively** on macOS, Linux, and Windows — no Docker, no external services.
The stack is: Python FastAPI server + Astro dashboard + SQLite (relational) + Turbovec (vector search).

---

## Prerequisites

| Tool | Purpose |
|------|---------|
| `uv` | Python dependency management |
| `bun` | Dashboard build (Astro) |
| `rust` + `cargo` | Tauri desktop app (optional) |

~4 GB disk for GGUF model files (downloaded automatically on first startup into `~/.minder/models/`).

---

## Quick Start

```bash
# 1. Install all dependencies and build the dashboard
make native-install

# 2. Start the server (dashboard + MCP API on port 8800)
make native-run
```

Open [http://localhost:8800/dashboard](http://localhost:8800/dashboard).

---

## Data Directories

All persistent state lives under `~/.minder/` (created automatically):

| Path | Contents |
|------|----------|
| `~/.minder/data/minder.db` | SQLite — users, sessions, workflows, repos |
| `~/.minder/data/vectors.tvim` | Turbovec — document embeddings (4-bit quantized ANN) |
| `~/.minder/data/graph.db` | SQLite — knowledge graph |
| `~/.minder/models/` | GGUF model cache |

---

## Dev Mode (hot reload)

```bash
uv run python scripts/dev_server.py
```

Watches `src/**/*.py`, `.env`, and `minder.toml` and restarts the server on any change.

Options:

```bash
uv run python scripts/dev_server.py --port 8810
uv run python scripts/dev_server.py --transport stdio
```

---

## Astro Dashboard Dev Mode

Run Astro on its own port for hot-reloaded frontend work:

```bash
bun run dev        # http://localhost:8808/dashboard
```

API calls go to `http://localhost:8800` (set `PUBLIC_API_URL` in `src/dashboard/.env`).

---

## Configuration

All settings live in `minder.toml` at the project root. Environment variables override any setting using `MINDER_<SECTION>__<KEY>`.

Key defaults:

```toml
[server]
port = 8800

[relational_store]
provider = "sqlite"
db_path = "~/.minder/data/minder.db"

[vector_store]
provider = "turbovec"

[turbovec]
db_path = "~/.minder/data/vectors.tvim"

[llm]
provider = "llama_cpp"
llama_cpp_model_repo = "unsloth/Qwen3.5-2B-GGUF"
llama_cpp_model_file = "Qwen3.5-2B-Q4_K_M.gguf"
```

To use OpenAI instead of llama-cpp:

```bash
MINDER_LLM__PROVIDER=openai OPENAI_API_KEY=sk-... uv run python -m minder.server
```

---

## First-Run Setup

1. Start the server (`make native-run`)
2. Open [http://localhost:8800/dashboard/setup](http://localhost:8800/dashboard/setup)
3. Enter email, username, display name
4. Copy the `mk_...` admin API key shown once on the success page
5. Sign in at [http://localhost:8800/dashboard/login](http://localhost:8800/dashboard/login)

---

## MCP SSE Verification

```bash
curl -N http://localhost:8800/sse
```

Expected:

```
event: endpoint
data: /messages/?session_id=...
```

---

## stdio MCP Mode

```bash
export MINDER_CLIENT_API_KEY="mkc_..."
MINDER_SERVER__TRANSPORT=stdio uv run python -m minder.server
```

---

## Tauri Desktop App (Optional)

The Tauri shell provides a native desktop window that manages the Python server as a sidecar process.

**Development mode** (requires Python server already running):

```bash
make app-dev
```

**Production build** (bundles PyInstaller binary + Tauri):

```bash
make bundle      # build PyInstaller binary
make app-build   # build .dmg (macOS), .AppImage/.deb (Linux), or .exe setup (Windows)
```

See [Native App Migration](../roadmap/native-app-migration.md) for full architecture details.

---

## Route Map

| Route | Purpose |
|-------|---------|
| `/dashboard/setup` | First-run admin bootstrap |
| `/dashboard/login` | Admin login |
| `/dashboard/clients` | Client registry, MCP config snippets |
| `/dashboard/instruction` | Agent orchestration rules |
| `/dashboard/sessions` | Session management |
| `/dashboard/memories` | Memory browser |
| `/dashboard/skills` | Skill catalog |
| `/dashboard/agents` | SubAgent registry |
| `/dashboard/chat` | Browser chat |
| `/dashboard/repositories` | Repo graph explorer |
| `/dashboard/workflows` | Workflow definitions |
| `/dashboard/observability` | Audit and trace |
| `/v1/admin/*` | Admin APIs |
| `/v1/auth/token-exchange` | Client key → bearer token |
| `/sse` | MCP SSE entrypoint |
| `/mcp` | MCP streamable HTTP entrypoint |

---

## Troubleshooting

### Models are not downloading

GGUF models download automatically via HuggingFace Hub on first startup. Check:

```bash
ls ~/.minder/models/
# or
ls ~/.cache/huggingface/hub/
```

If download fails due to rate limits, set `HF_TOKEN`:

```bash
HF_TOKEN=hf_... uv run python -m minder.server
```

### Server fails to start

Run directly for full error output:

```bash
uv run python -m minder.server
```

Common causes:
- Python < 3.14 (check `python --version`)
- Missing server extra: run `uv sync --extra server`
- Port 8800 already in use: set `MINDER_SERVER__PORT=8810`

### Lost admin API key

```bash
uv run python scripts/reset_admin_api_key.py --username admin
```

Prints a new `mk_...` key and invalidates the old one.

### First-run setup page already used

Once an admin exists, `/dashboard/setup` is locked. Use `/dashboard/login` directly.
