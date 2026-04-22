# Local Setup Guide

This guide gets the local dependency stack running so you can debug Minder and the Astro dashboard against real backing services.

It uses one local development shape:

- Docker for infra services only
- local Python for Minder
- optional local Astro dev server for dashboard work

System-level architecture lives in:

- [System Design](../../docs/system-design.md)

## Prerequisites

- Docker Desktop or compatible Docker runtime
- `uv`
- enough disk for MongoDB, Redis, Milvus, Ollama container, and LiteRT-LM model files

## 1. Download the LiteRT-LM model

Run:

```bash
./scripts/download_models.sh
```

This script stores models in:

```text
~/.minder/models
```

Expected files:

```text
~/.minder/models/gemma-4-E2B-it.litertlm
~/.minder/models/embeddinggemma-300M-Q8_0.gguf  (offline fallback)
```

Note: The primary embedding model (`embeddinggemma:300m`) is auto-pulled by the Docker Ollama container. The GGUF file above is an offline fallback only.

## 1a. Create local env files

Backend:

```bash
cp .env.example .env
```

Frontend:

```bash
cp src/dashboard/.env.example src/dashboard/.env
```

The example files already target:

- Minder backend on `8800`
- Astro dev server on `8808`
- dashboard API calls to `http://localhost:8800`

## 2. Start the local infrastructure stack

Run:

```bash
docker compose -f docker/docker-compose.local.yml up -d
```

The stack exposes:

- MongoDB: `localhost:27017`
- Redis: `localhost:6379`
- Milvus: `localhost:19530`

Wait until all infra services are healthy.

Recommended check:

```bash
docker compose -f docker/docker-compose.local.yml ps
```

Local Docker now provides the shared infra runtime:

- `ollama` (embedding inference)
- `ollama-init` (auto-pull embedding model)
- `mongodb`
- `redis`
- `etcd`
- `minio`
- `milvus-standalone`

It intentionally does not start the Minder app or the Astro dashboard. You run those locally so you can debug them directly.

LLM inference runs on the host via LiteRT-LM (no Docker required for LLM).

## 2a. Start Minder locally against the Docker infra

Start Minder with hot reload:

```bash
uv run python scripts/dev_server.py
```

This launcher watches `src/**/*.py`, `.env`, and `minder.toml`, then restarts Minder automatically after code or config changes.

Useful options:

```bash
uv run python scripts/dev_server.py --port 8810
uv run python scripts/dev_server.py --transport stdio
```

If you need the old production-like one-shot entrypoint, you can still run:

```bash
PYTHONPATH=src UV_CACHE_DIR=.uv-cache uv run python -m minder.server
```

Open after Minder starts:

- [http://localhost:8800/dashboard](http://localhost:8800/dashboard)
- [http://localhost:8800/sse](http://localhost:8800/sse)

## 2b. Optional Astro frontend-dev mode

Start Astro:

```bash
cd src/dashboard
bun install
bun run dev
```

Open:

- [http://localhost:8808/dashboard](http://localhost:8808/dashboard)

Important behavior:

- Astro runs on `8808`
- Minder APIs stay on `8800`
- the frontend calls Minder through `API_URL` from `src/dashboard/.env`
- Astro bridges `API_URL` into the browser-safe `PUBLIC_API_URL`
- onboarding snippets and connection-test templates use the backend origin seen by Minder, so in split mode they resolve to `http://localhost:8800`
- when Astro is not running, Minder can still serve the built dashboard on the same origin if you already built `src/dashboard`
- in production, `/dashboard/*` is served by the dedicated Astro service behind the gateway

## 3. Open the first-run setup page

On a fresh deployment with no admin users, open:

- [http://localhost:8800/dashboard/setup](http://localhost:8800/dashboard/setup)

Fill in:

- email
- username
- display name

On success, Minder redirects to a setup-complete page and reveals the bootstrap admin API key once.

Save the `mk_...` value before leaving that page.

If an admin already exists, `/dashboard/setup` is no longer the right entrypoint and you should use `/dashboard/login` instead.

## 4. Sign in to the dashboard

Open:

- [http://localhost:8800/dashboard/login](http://localhost:8800/dashboard/login)

Paste the `mk_...` admin API key from the setup-complete page.

On success, the browser is redirected to:

- [http://localhost:8800/dashboard](http://localhost:8800/dashboard)

The dashboard session is stored in an `HttpOnly` cookie.

## 5. Verify the SSE server is up

Run:

```bash
curl -N http://localhost:8800/sse
```

Expected output starts like this:

```text
event: endpoint
data: /messages/?session_id=...
```

If you see that, the MCP SSE server is reachable.

## 6. Verify the direct stdio bootstrap path

For local stdio-based MCP clients, export a client key and start Minder in stdio mode:

```bash
export MINDER_CLIENT_API_KEY="mkc_..."
MINDER_SERVER__TRANSPORT=stdio UV_CACHE_DIR=.uv-cache uv run python -m minder.server
```

Protected tool calls can now resolve the client principal directly from `MINDER_CLIENT_API_KEY` without a token-exchange pre-step.

## 7. Move to onboarding

Continue with:

- [Admin and Client Onboarding Guide](../../docs/guides/admin-client-onboarding.md)

## Route Map

- `/dashboard/setup`: first-run admin bootstrap
- `/dashboard/login`: admin browser login
- `/dashboard/clients`: Astro client registry and detail shell
- `/v1/admin/*`: admin JSON APIs used by the dashboard
- `/v1/auth/token-exchange`: client key to bearer token exchange
- `/sse`: MCP SSE entrypoint

Split frontend-dev URL map:

- `http://localhost:8808/dashboard/*`: Astro dev console
- `http://localhost:8800/v1/admin/*`: admin APIs
- `http://localhost:8800/v1/auth/*`: auth APIs
- `http://localhost:8800/sse`: MCP SSE entrypoint

## Troubleshooting

### Models are missing

Check:

```bash
ls ~/.minder/models
```

### Minder process cannot boot

Check:

```bash
PYTHONPATH=src UV_CACHE_DIR=.uv-cache uv run python -m minder.server
```

### I lost the first admin API key

Run:

```bash
PYTHONPATH=src UV_CACHE_DIR=.uv-cache uv run python scripts/reset_admin_api_key.py \
  --username admin
```

The command rotates the admin API key and prints the new `mk_...` value once.

### I need to verify browser onboarding again

Open these routes in order:

- [http://localhost:8800/dashboard/setup](http://localhost:8800/dashboard/setup)
- [http://localhost:8800/dashboard/login](http://localhost:8800/dashboard/login)
- [http://localhost:8800/dashboard](http://localhost:8800/dashboard)

### SSE does not respond

Check:

```bash
curl http://localhost:8800/sse
```

and confirm the container is running:

```bash
docker compose -f docker/docker-compose.local.yml ps
```
