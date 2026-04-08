# Admin and Client Onboarding Guide

This guide covers the current onboarding flow for Minder on local Docker.

## Current Reality

Today you can:

- create an admin
- sign into `/dashboard/login` in the browser with the admin API key
- create MCP clients
- generate client API keys
- exchange a client key for an access token
- onboard `Codex`, `Copilot-style MCP clients`, and `Claude Desktop`

Today you cannot yet:

- manage everything from a polished production dashboard UI

The current admin bootstrap is still API-key based, but once the first admin key exists, browser login is available.

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

## 2. Sign into the browser dashboard

Open:

- [http://localhost:8800/dashboard/login](http://localhost:8800/dashboard/login)

Enter the admin API key:

```text
mk_...
```

After successful sign-in, the browser is redirected to:

- [http://localhost:8800/dashboard](http://localhost:8800/dashboard)

The dashboard session is stored in an `HttpOnly` cookie.

## 3. Use the admin session or admin JWT against admin routes

For browser-based dashboard use, the login cookie is enough.

For API clients like `curl`, Postman, or Bruno, bearer auth is still useful.

If you need an admin JWT through MCP, the current codebase still exposes `minder_auth_login`.

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

## 8. Open the dashboard

The dashboard is at:

- [http://localhost:8800/dashboard](http://localhost:8800/dashboard)

If you already signed in at `/dashboard/login`, the dashboard opens with the browser session cookie.

## 9. Revoke a client key

If a client key is leaked or rotated, call the revoke endpoint from the admin surface. That endpoint is already available in the backend and covered by tests.

## Recommended Operator Flow

1. Start the Docker stack.
2. Create the first admin.
3. Create one client per real MCP consumer.
4. Scope each client to the smallest needed tool set.
5. Use onboarding templates from the admin API, not handwritten config.
6. Rotate client keys when a workstation or integration changes ownership.
