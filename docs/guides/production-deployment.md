# Production Deployment Guide

This guide deploys Minder behind a single public gateway on one port:

- MCP server on `SSE`
- Astro admin console on `/dashboard`
- Admin and client APIs on `/v1/...`

The browser still uses one public origin on `:8800`, but production now runs three internal services:

- `gateway` on public `8800`
- `dashboard` on internal `8808`
- `minder-api` on internal `8801`

Local split frontend development on `8808` is a development-only workflow and is not part of the production shape.
Do not copy the split local frontend `.env` workflow into production images.

Canonical runtime and deployment architecture:

- [System Design](../../docs/system-design.md)

## What the Production Stack Builds

The production stack uses:

1. [docker/Dockerfile.api](../../docker/Dockerfile.api) for the Python API runtime
2. [docker/Dockerfile.dashboard](../../docker/Dockerfile.dashboard) for the Astro standalone runtime
3. [docker/Caddyfile](../../docker/Caddyfile) as the public routing layer

At runtime:

- `/dashboard/*` is served by the Astro service
- `/v1/*`, `/sse`, `/messages/*`, and `/setup` are served by the Python API service
- the browser still sees a single origin on `http://host:8800`

## Prerequisites

- Docker Engine or Docker Desktop
- local Qwen GGUF files under `~/.minder/models`
- enough memory for MongoDB, Redis, Milvus, and local inference
- `Bun 1.2.21` for local dashboard work
- `Node 22.12+` only if you run frontend tooling outside Bun

Expected local model files:

```text
~/.minder/models/qwen3-embedding-0.6b.Q8_0.gguf
~/.minder/models/qwen3.5-0.8b-instruct.Q4_K_M.gguf
```

## 1. Build and Start the Production Stack

Run:

```bash
docker compose -f docker/docker-compose.yml up --build -d
```

If you want to build the dashboard locally before packaging:

```bash
cd src/dashboard
bun install
bun run build
```

The public gateway will listen on:

- [http://localhost:8800/dashboard](http://localhost:8800/dashboard)
- [http://localhost:8800/sse](http://localhost:8800/sse)

## 2. Bootstrap the First Admin

Open:

- [http://localhost:8800/dashboard/setup](http://localhost:8800/dashboard/setup)

Fill in:

- username
- email
- display name

Minder will show the bootstrap admin API key one time only. Save the `mk_...` value before leaving the page.

## 3. Sign In

Open:

- [http://localhost:8800/dashboard/login](http://localhost:8800/dashboard/login)

Use the saved `mk_...` admin API key.

## 4. Create and Onboard a Client

After login:

1. Open the client registry at [http://localhost:8800/dashboard/clients](http://localhost:8800/dashboard/clients)
2. Create a client
3. Save the one-time `mkc_...` client API key
4. Open the client detail view
5. Copy the onboarding snippet for `Codex`, `Copilot-style MCP`, or `Claude Desktop`

## 5. Verify SSE Access

Run:

```bash
curl -N http://localhost:8800/sse
```

Expected output begins with:

```text
event: endpoint
data: /messages/?session_id=...
```

## 6. Recover an Admin Key

If the admin key is lost:

```bash
docker compose -f docker/docker-compose.yml exec minder-api \
  uv run python scripts/reset_admin_api_key.py \
  --username admin
```

The old key is invalid immediately after rotation.

## Important Runtime Settings

The production compose file sets:

- `gateway` as the only public port binder on `8800`
- `MINDER_SERVER__PORT=8801` for `minder-api`
- `dashboard` runtime on internal `8808`
- `MINDER_DASHBOARD__BASE_PATH=/dashboard` so backend redirects and onboarding URLs stay aligned

## Upgrade Workflow

For a new release:

```bash
docker compose -f docker/docker-compose.yml pull
docker compose -f docker/docker-compose.yml up --build -d
```

If you build from source locally:

```bash
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d
```

## Health Checks

Recommended checks:

```bash
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs gateway
docker compose -f docker/docker-compose.yml logs dashboard
docker compose -f docker/docker-compose.yml logs minder-api
docker compose -f docker/docker-compose.yml logs mongodb
docker compose -f docker/docker-compose.yml logs redis
docker compose -f docker/docker-compose.yml logs milvus-standalone
```

## Rollback

Rollback is image-based:

1. switch `MINDER_IMAGE_TAG`
2. redeploy `docker compose -f docker/docker-compose.yml up -d`

The public contract remains single-port because the gateway still owns `:8800`.
