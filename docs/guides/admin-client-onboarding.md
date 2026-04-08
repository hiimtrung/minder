# Admin and Client Onboarding Guide

This guide covers the current onboarding flow for Minder on local Docker.

## Current Reality

Today you can:

- create an admin
- create MCP clients
- generate client API keys
- exchange a client key for an access token
- onboard `Codex`, `Copilot-style MCP clients`, and `Claude Desktop`

Today you cannot yet:

- log into the dashboard with a browser form
- manage everything from a polished production dashboard UI

The current admin bootstrap is still API-key based.

## 1. Create the admin user

If you have not done this yet:

```bash
docker compose -f docker/docker-compose.dev.yml exec minder \
  uv run python scripts/create_admin.py \
  --email admin@example.com \
  --username admin \
  --display-name "Admin"
```

Save the returned admin API key:

```text
mk_...
```

## 2. Get an admin JWT through MCP

The current codebase exposes admin login as the MCP tool `minder_auth_login`.

### 2.1 Open the SSE stream

Run:

```bash
curl -N http://localhost:8800/sse
```

Expected output starts like this:

```text
event: endpoint
data: /messages/?session_id=...
```

Copy the `data:` value and turn it into a full URL:

```text
http://localhost:8800/messages/?session_id=...
```

Call that value `MESSAGE_URL`.

### 2.2 Initialize the MCP session

```bash
curl -X POST "$MESSAGE_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 0,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {
        "name": "manual-admin-client",
        "version": "1.0.0"
      }
    }
  }'
```

Then notify initialization complete:

```bash
curl -X POST "$MESSAGE_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "notifications/initialized"
  }'
```

### 2.3 Login with the admin API key

```bash
curl -X POST "$MESSAGE_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "minder_auth_login",
      "arguments": {
        "api_key": "mk_..."
      }
    }
  }'
```

The response contains:

- `token`
- `user_id`

Save the `token`. That is your admin JWT.

## 3. Use the admin JWT against HTTP admin routes

Once you have a JWT, send it as:

```text
Authorization: Bearer <jwt>
```

This JWT is required for:

- `GET /dashboard`
- `GET /v1/admin/clients`
- `POST /v1/admin/clients`
- `GET /v1/admin/onboarding/{client_id}`
- `GET /v1/admin/audit`

Practical note:

- a browser tab cannot conveniently inject this header on its own
- for now, use `curl`, Postman, Bruno, or another API client for the admin surface
- the broader `Phase 4` backlog still includes a real browser login flow

## 4. Create an MCP client

Example:

```bash
curl -X POST http://localhost:8800/v1/admin/clients \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <jwt>" \
  -d '{
    "name": "Codex Local",
    "slug": "codex-local",
    "description": "Local Codex workstation",
    "tool_scopes": ["minder_query", "minder_search_code", "minder_search_errors"],
    "repo_scopes": ["*"]
  }'
```

The response includes:

- client metadata
- a newly issued `client_api_key` starting with `mkc_`

Save the `mkc_...` value. That is what MCP clients should use.

## 5. Get onboarding templates for the client

Run:

```bash
curl http://localhost:8800/v1/admin/onboarding/<client_id> \
  -H "Authorization: Bearer <jwt>"
```

This returns templates for:

- `codex`
- `copilot`
- `claude_desktop`

All templates now default to:

```text
http://localhost:8800/sse
```

## 6. Exchange a client API key for an access token

Run:

```bash
curl -X POST http://localhost:8800/v1/auth/token-exchange \
  -H "Content-Type: application/json" \
  -d '{
    "client_api_key": "mkc_..."
  }'
```

Expected response:

```json
{
  "access_token": "<token>",
  "token_type": "bearer",
  "expires_in": 3600,
  "client": {
    "slug": "codex-local"
  }
}
```

## 7. Connect an MCP client

### Codex-style bootstrap payload

```json
{
  "server_url": "http://localhost:8800/sse",
  "client_api_key": "mkc_...",
  "bootstrap_path": "/v1/auth/token-exchange",
  "client_slug": "codex-local",
  "preferred_tool": "minder_query"
}
```

### Copilot-style MCP snippet

```json
{
  "type": "mcp",
  "url": "http://localhost:8800/sse",
  "headers": {
    "X-Minder-Client-Key": "mkc_..."
  },
  "client": "codex-local"
}
```

### Claude Desktop-style snippet

```json
{
  "mcpServers": {
    "minder": {
      "url": "http://localhost:8800/sse",
      "headers": {
        "X-Minder-Client-Key": "mkc_..."
      },
      "client": "codex-local"
    }
  }
}
```

## 8. Optional: open the dashboard

The dashboard is at:

- [http://localhost:8800/dashboard](http://localhost:8800/dashboard)

But it still requires:

```text
Authorization: Bearer <jwt>
```

So today it is better thought of as a protected admin route than a complete browser-login product screen.

## 9. Revoke a client key

If a client key is leaked or rotated, call the revoke endpoint from the admin surface. That endpoint is already available in the backend and covered by tests.

## Recommended Operator Flow

1. Start the Docker stack.
2. Create the first admin.
3. Create one client per real MCP consumer.
4. Scope each client to the smallest needed tool set.
5. Use onboarding templates from the admin API, not handwritten config.
6. Rotate client keys when a workstation or integration changes ownership.
