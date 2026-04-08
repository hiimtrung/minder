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
- Dashboard: [http://localhost:8800/dashboard](http://localhost:8800/dashboard)
- MongoDB: `localhost:27017`
- Redis: `localhost:6379`
- Milvus: `localhost:19530`

Wait until all services are healthy and `docker-minder-1` is started.

## 3. Create the first admin

In another terminal:

```bash
docker compose -f docker/docker-compose.dev.yml exec minder \
  uv run python scripts/create_admin.py \
  --email admin@example.com \
  --username admin \
  --display-name "Admin"
```

You should see either:

```text
Admin created: <uuid>
API key: mk_...
```

or:

```text
Admin already exists: <uuid>
```

If the admin already exists, you need the original `mk_...` key that was issued when the admin was first created.

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

### SSE does not respond

Check:

```bash
curl http://localhost:8800/sse
```

and confirm the container is running:

```bash
docker compose -f docker/docker-compose.dev.yml ps
```
