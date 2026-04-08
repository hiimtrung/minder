# Local Setup Guide

This guide gets a fresh Minder stack running locally on port `8800`.

## Prerequisites

- Docker Desktop or compatible Docker runtime
- `uv`
- enough disk for MongoDB, Redis, Milvus, and GGUF model files

## 1. Download the local models

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
~/.minder/models/qwen3-embedding-0.6b.Q8_0.gguf
~/.minder/models/qwen3.5-0.8b-instruct.Q4_K_M.gguf
```

## 2. Start the Docker stack

Run:

```bash
docker compose -f docker/docker-compose.dev.yml up --build
```

The stack exposes:

- Minder SSE: [http://localhost:8800/sse](http://localhost:8800/sse)
- Minder admin login: [http://localhost:8800/dashboard/login](http://localhost:8800/dashboard/login)
- Dashboard: [http://localhost:8800/dashboard](http://localhost:8800/dashboard)
- MongoDB: `localhost:27017`
- Redis: `localhost:6379`
- Milvus: `localhost:19530`

Wait until all services are healthy and `docker-minder-1` is started.

## 3. Open the first-run setup page

On a fresh deployment with no admin users, open:

- [http://localhost:8800/setup](http://localhost:8800/setup)

Fill in:

- email
- username
- display name

On success, Minder redirects to a setup-complete page and reveals the bootstrap admin API key once.

Save the `mk_...` value before leaving that page.

If an admin already exists, `/setup` is disabled and you should use `/dashboard/login` instead.

## 4. Verify the server is up

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

## 5. Move to onboarding

Continue with:

- [Admin and Client Onboarding Guide](/Users/trungtran/ai-agents/minder/docs/guides/admin-client-onboarding.md)

## Troubleshooting

### Models are missing

Check:

```bash
ls ~/.minder/models
```

### Minder container cannot boot

Check:

```bash
docker compose -f docker/docker-compose.dev.yml logs minder
```

### I lost the first admin API key

At the moment, first-run browser setup exists, but the dedicated recovery script is still pending. Until that lands, use the originally saved admin key or rotate access through an existing authenticated admin path.

### SSE does not respond

Check:

```bash
curl http://localhost:8800/sse
```

and confirm the container is running:

```bash
docker compose -f docker/docker-compose.dev.yml ps
```
