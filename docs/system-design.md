# System Design

This document is the canonical system-design reference for Minder.

Use it for:

- overall architecture
- runtime and deployment shape
- clean architecture boundaries
- storage and retrieval topology
- dashboard and MCP integration flow
- links to deeper feature-specific design documents

## 1. System Overview

Minder is an MCP-first engineering assistant platform with:

- an Astro admin console
- an MCP gateway over `SSE` and `stdio`
- admin APIs for onboarding and client management
- repository-aware retrieval, workflow, memory, and session tools
- operational data in `MongoDB`
- cache, rate limiting, and client sessions in `Redis`
- vector search in `Milvus Standalone`
- local GGUF inference through `llama-cpp-python`

## 2. Runtime Architecture

```mermaid
flowchart TB
  Browser["Browser Admin :8800"] --> Gateway["Gateway Proxy"]
    MCP["Codex / Copilot / Claude / stdio Clients"] --> Gateway["MCP Gateway<br/>SSE / stdio"]

  Gateway --> Dashboard["Astro Dashboard Service<br/>/dashboard/*"]
  Gateway --> AdminHTTP["Admin HTTP Presentation<br/>/v1/admin/*"]
  Gateway --> TokenHTTP["Token Exchange / Gateway Test<br/>/v1/auth/* /v1/gateway/*"]
    Gateway --> ToolSurface["MCP Tool Surface"]

    AdminHTTP --> UseCases["Application Use Cases"]
    TokenHTTP --> UseCases
    ToolSurface --> UseCases

    UseCases --> Auth["Auth / RBAC / Rate Limits"]
    UseCases --> Workflow["Workflow / Memory / Session / Query Services"]

    Workflow --> Mongo["MongoDB"]
    Workflow --> Redis["Redis"]
    Workflow --> Milvus["Milvus Standalone"]
    Workflow --> LLM["Qwen GGUF via llama.cpp"]
    Models["~/.minder/models"] --> LLM
```

## 3. Dashboard Runtime Modes

Minder supports two dashboard runtime modes.

### Containerized Production: Reverse-Proxy Split Runtime

The Astro console runs as a separate service in production, but the browser still sees a single public origin on port `8800`.

The deployment model is:

```mermaid
flowchart LR
  Browser["Browser :8800"] --> Proxy["Gateway Proxy :8800"]
  Proxy --> Astro["Astro service :8808"]
  Proxy --> Python["Python API :8801"]
  Python --> MCP["MCP /sse and stdio"]
```

At runtime:

- the gateway is the only public port binder on `8800`
- Astro owns all `/dashboard/*` routes directly
- the Python API owns `/v1/*`, `/sse`, `/messages/*`, `/setup`, and related backend routes
- same-origin browser behavior is preserved through reverse proxying

### Local Frontend Development: Split Runtime

For local frontend work, Astro can run separately from Minder:

```mermaid
flowchart LR
    AstroDev["Astro dev server :8808<br/>API_URL=http://localhost:8800"] --> Browser["Browser /dashboard"]
    Browser --> Backend["Python app :8800"]
    Backend --> Mongo["MongoDB"]
    Backend --> Redis["Redis"]
    Backend --> Milvus["Milvus"]
```

In this mode:

- Astro dev server runs on `8808`
- Minder backend stays on `8800`
- dashboard API calls go to `API_URL`
- Astro maps `API_URL` into the client-visible `PUBLIC_API_URL` during dev/build
- onboarding snippets use the backend origin seen on the API request, which makes local snippets point to `8800`
- when `dashboard.dev_server_url` is configured, backend dashboard routes redirect to the Astro dev server instead of serving compatibility static files

### Compatibility Static Serving

Backend-served static dashboard assets still exist as a compatibility/testing mode, but this is no longer the recommended production deployment shape.

## 4. Clean Architecture Boundaries

```mermaid
flowchart LR
    Presentation["Presentation Layer"]
    Application["Application Layer"]
    Domain["Domain Policies / Models"]
    Infrastructure["Infrastructure Adapters"]

    Presentation --> Application
    Application --> Domain
    Application --> Infrastructure
    Infrastructure --> Domain
```

### Presentation

- [`src/minder/presentation/http/admin/routes.py`](../src/minder/presentation/http/admin/routes.py)
- [`src/minder/presentation/http/admin/api.py`](../src/minder/presentation/http/admin/api.py)
- [`src/minder/presentation/http/admin/dashboard.py`](../src/minder/presentation/http/admin/dashboard.py)
- [`src/minder/presentation/http/admin/context.py`](../src/minder/presentation/http/admin/context.py)

`routes.py` still exists because it is the composition boundary for the admin HTTP presentation layer.
It no longer owns old Python-rendered dashboard HTML.

Responsibilities are now split as:

- `routes.py`: route composition only
- `api.py`: JSON admin APIs
- `dashboard.py`: compatibility static dashboard serving and redirect policy
- `context.py`: shared request/auth/use-case context

### Application

- [`src/minder/application/admin/use_cases.py`](../src/minder/application/admin/use_cases.py)
- [`src/minder/application/admin/dto.py`](../src/minder/application/admin/dto.py)

### Infrastructure

- [`src/minder/store`](../src/minder/store)
- [`src/minder/auth`](../src/minder/auth)
- [`src/minder/transport`](../src/minder/transport)

## 5. Storage Topology

```mermaid
flowchart LR
    App["Minder App"] --> Mongo["MongoDB<br/>operational data"]
    App --> Redis["Redis<br/>cache / rate limit / sessions"]
    App --> Milvus["Milvus Standalone<br/>vector search"]
    App --> RepoState[".minder repo-local state"]
```

### MongoDB

Primary operational store for:

- users
- clients
- API key metadata
- audit events
- workflow-adjacent application records

### Redis

Used for:

- client session caching
- admin/session support
- rate limiting
- ephemeral cache

### Milvus

Used for:

- embeddings
- semantic retrieval
- vector-backed repository/document search

## 6. Admin and Client Auth Flow

```mermaid
flowchart LR
    Admin["Admin in Browser"] --> Setup["/dashboard/setup"]
    Setup --> AdminKey["Admin API Key (mk_...)"]
    AdminKey --> Login["/dashboard/login"]
    Login --> Session["HttpOnly Admin Session"]
    Session --> ClientRegistry["/dashboard/clients"]

    ClientRegistry --> ClientKey["Client API Key (mkc_...)"]
    ClientKey --> Direct["Direct client auth<br/>X-Minder-Client-Key / MINDER_CLIENT_API_KEY"]
    ClientKey --> Exchange["/v1/auth/token-exchange"]
    Exchange --> AccessToken["Short-lived Access Token"]

    Direct --> MCP["MCP Clients"]
    AccessToken --> MCP
```

## 7. Dashboard Integration Rules

The dashboard is not a blind static site. Python still controls route state.

Current behavior for compatibility mode:

- backend-served `/dashboard` routes can still redirect between setup/login/clients
- static assets under `/dashboard/_astro/...` bypass those redirects

Containerized production behavior:

- the gateway routes `/dashboard` and `/dashboard/*` to the Astro service
- Astro resolves `/dashboard` state through `GET /v1/admin/bootstrap-state`
- browser API calls stay same-origin through the gateway

Onboarding snippets and connection-test templates derive their base URL like this:

- local split-runtime mode: from the backend API request origin, which follows `API_URL`
- Docker and production static mode: from the current request origin on the same host

## 8. Frontend Structure

```mermaid
flowchart TB
    Layout["DashboardLayout.astro"] --> Setup["setup.astro"]
    Layout --> Login["login.astro"]
    Layout --> Entry["index.astro"]
    Layout --> Clients["clients/index.astro"]
    Layout --> ClientDetail["clients/[clientId].astro"]

    Entry --> EntryScript["scripts/dashboard-entry.ts"]
    Setup --> SetupScript["scripts/setup-page.ts"]
    Login --> LoginScript["scripts/login-page.ts"]
    Clients --> ClientsScript["scripts/clients-page.ts"]
    Layout --> SessionScript["scripts/session-header.ts"]

    SetupScript --> AdminApi["lib/api/admin.ts"]
    LoginScript --> AdminApi
    ClientsScript --> AdminApi
    SessionScript --> AdminApi
```

Key paths:

- [`src/dashboard/src/layouts/DashboardLayout.astro`](../src/dashboard/src/layouts/DashboardLayout.astro)
- [`src/dashboard/src/pages/setup.astro`](../src/dashboard/src/pages/setup.astro)
- [`src/dashboard/src/pages/login.astro`](../src/dashboard/src/pages/login.astro)
- [`src/dashboard/src/pages/index.astro`](../src/dashboard/src/pages/index.astro)
- [`src/dashboard/src/pages/clients/index.astro`](../src/dashboard/src/pages/clients/index.astro)
- [`src/dashboard/src/pages/clients/[clientId].astro`](../src/dashboard/src/pages/clients/[clientId].astro)
- [`src/dashboard/src/scripts/dashboard-entry.ts`](../src/dashboard/src/scripts/dashboard-entry.ts)
- [`src/dashboard/src/scripts/clients-page.ts`](../src/dashboard/src/scripts/clients-page.ts)
- [`src/dashboard/src/lib/api/admin.ts`](../src/dashboard/src/lib/api/admin.ts)

## 9. Deployment Shape

### Local / Dev

- [`docker/docker-compose.local.yml`](../docker/docker-compose.local.yml)
- infra-only Docker services for MongoDB, Redis, Milvus, etcd, and minio
- Minder and Astro run outside Docker for interactive debugging

### Production

- [`docker/docker-compose.yml`](../docker/docker-compose.yml)
- [`docker/Dockerfile.api`](../docker/Dockerfile.api)
- [`docker/Dockerfile.dashboard`](../docker/Dockerfile.dashboard)
- [`docker/Caddyfile`](../docker/Caddyfile)
- services:
  - `gateway` on public `8800`
  - `dashboard` on internal `8808`
  - `minder-api` on internal `8801`

## 10. Related Design Documents

Feature-specific design docs still exist and remain useful, but this file is the system-level source of truth.

- [Gateway Auth and Dashboard Design](../docs/design/mcp-gateway-auth-dashboard.md)
- [Phase 4.3 Console Clean Architecture and UI Modernization](../docs/design/p4_3_console_clean_architecture_and_ui_modernization.md)
- [Production Dashboard Reverse Proxy Split](../docs/design/production_dashboard_reverse_proxy_split.md)
- [Plan 02: Architecture](../docs/plan/02-architecture.md)
