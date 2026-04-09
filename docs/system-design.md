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
- an Astro admin console served by the Python app
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
    Browser["Browser Admin"] --> Dashboard["Astro Dashboard<br/>/dashboard"]
    MCP["Codex / Copilot / Claude / stdio Clients"] --> Gateway["MCP Gateway<br/>SSE / stdio"]

    Dashboard --> AdminHTTP["Admin HTTP Presentation<br/>/v1/admin/*"]
    Dashboard --> TokenHTTP["Token Exchange / Gateway Test<br/>/v1/auth/* /v1/gateway/*"]
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

## 3. Single-Port Dashboard Serving

The Astro console does not run as a separate runtime in production.

The deployment model is:

```mermaid
flowchart LR
    AstroSource["Astro source<br/>src/dashboard"] --> Build["bun build"]
    Build --> StaticAssets["Static assets<br/>dashboard-dist or src/dashboard/dist"]
    StaticAssets --> Python["Python app :8800"]
    Python --> Browser["Browser /dashboard"]
    Python --> MCP["MCP /sse and stdio"]
```

At runtime:
- Astro is already built
- Python is the only server binding port `8800`
- Python serves the static dashboard assets and all admin/MCP APIs on the same origin

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

- [`src/minder/presentation/http/admin/routes.py`](/Users/trungtran/ai-agents/minder/src/minder/presentation/http/admin/routes.py)
- [`src/minder/presentation/http/admin/api.py`](/Users/trungtran/ai-agents/minder/src/minder/presentation/http/admin/api.py)
- [`src/minder/presentation/http/admin/dashboard.py`](/Users/trungtran/ai-agents/minder/src/minder/presentation/http/admin/dashboard.py)
- [`src/minder/presentation/http/admin/context.py`](/Users/trungtran/ai-agents/minder/src/minder/presentation/http/admin/context.py)

`routes.py` still exists because it is the composition boundary for the admin HTTP presentation layer.
It no longer owns old Python-rendered dashboard HTML.

Responsibilities are now split as:
- `routes.py`: route composition only
- `api.py`: JSON admin APIs
- `dashboard.py`: Astro/static dashboard serving and redirect policy
- `context.py`: shared request/auth/use-case context

### Application

- [`src/minder/application/admin/use_cases.py`](/Users/trungtran/ai-agents/minder/src/minder/application/admin/use_cases.py)
- [`src/minder/application/admin/dto.py`](/Users/trungtran/ai-agents/minder/src/minder/application/admin/dto.py)

### Infrastructure

- [`src/minder/store`](/Users/trungtran/ai-agents/minder/src/minder/store)
- [`src/minder/auth`](/Users/trungtran/ai-agents/minder/src/minder/auth)
- [`src/minder/transport`](/Users/trungtran/ai-agents/minder/src/minder/transport)

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

Current behavior:
- no admin exists:
  - `/dashboard` -> `/dashboard/setup`
- admin exists but no valid session:
  - `/dashboard` -> `/dashboard/login`
- valid admin session exists:
  - `/dashboard` -> `/dashboard/clients`
- static assets under `/dashboard/_astro/...` bypass those redirects

Onboarding snippets and connection-test templates now derive their base URL from the current request origin, so deployed domains appear correctly instead of hardcoded `localhost`.

## 8. Frontend Structure

```mermaid
flowchart TB
    Layout["DashboardLayout.astro"] --> Setup["setup.astro"]
    Layout --> Login["login.astro"]
    Layout --> Clients["clients/index.astro"]

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
- [`src/dashboard/src/layouts/DashboardLayout.astro`](/Users/trungtran/ai-agents/minder/src/dashboard/src/layouts/DashboardLayout.astro)
- [`src/dashboard/src/pages/setup.astro`](/Users/trungtran/ai-agents/minder/src/dashboard/src/pages/setup.astro)
- [`src/dashboard/src/pages/login.astro`](/Users/trungtran/ai-agents/minder/src/dashboard/src/pages/login.astro)
- [`src/dashboard/src/pages/clients/index.astro`](/Users/trungtran/ai-agents/minder/src/dashboard/src/pages/clients/index.astro)
- [`src/dashboard/src/scripts/clients-page.ts`](/Users/trungtran/ai-agents/minder/src/dashboard/src/scripts/clients-page.ts)
- [`src/dashboard/src/lib/api/admin.ts`](/Users/trungtran/ai-agents/minder/src/dashboard/src/lib/api/admin.ts)

## 9. Deployment Shape

### Local / Dev

- [`docker/docker-compose.dev.yml`](/Users/trungtran/ai-agents/minder/docker/docker-compose.dev.yml)
- one app port: `8800`
- Docker services for Minder, MongoDB, Redis, Milvus, etcd, minio

### Production

- [`docker/docker-compose.prod.yml`](/Users/trungtran/ai-agents/minder/docker/docker-compose.prod.yml)
- multi-stage build:
  - `bun` builds Astro
  - `python` serves built assets and APIs

## 10. Related Design Documents

Feature-specific design docs still exist and remain useful, but this file is the system-level source of truth.

- [Gateway Auth and Dashboard Design](/Users/trungtran/ai-agents/minder/docs/design/mcp-gateway-auth-dashboard.md)
- [Phase 4.3 Console Clean Architecture and UI Modernization](/Users/trungtran/ai-agents/minder/docs/design/p4_3_console_clean_architecture_and_ui_modernization.md)
- [Plan 02: Architecture](/Users/trungtran/ai-agents/minder/docs/plan/02-architecture.md)
