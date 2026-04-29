# Requirements: Phase 4.1 Dashboard Setup & Direct MCP Client Auth

**Date**: 2026-04-08
**Status**: Implemented
**Author**: BA

---

## Goal

Close the remaining onboarding gaps between the current Phase 4.0 gateway/dashboard baseline and a truly low-friction production operator experience.

This phase must:

- remove the need to `docker exec` into the container just to create the first admin
- provide a supported access recovery path for the dashboard admin model that already uses API keys
- make direct MCP client authentication fully first-class across transports, so IDE clients can use a single `client_api_key` without custom token-exchange wrappers

---

## Current Baseline

The current codebase already provides:

- `GET /dashboard/login` and `/dashboard` browser login flow using an admin API key and an `HttpOnly` JWT cookie
- `scripts/create_admin.py` for bootstrap of the first admin
- `POST /v1/auth/token-exchange` for client token exchange
- direct SSE support for `X-Minder-Client-Key`
- admin routes for client creation, key rotation, revocation, onboarding templates, and audit access

The current codebase still lacks:

- first-run setup wizard for a brand-new deployment
- a supported admin access recovery command aligned to the API-key auth model
- direct `client_api_key` parity across all supported MCP transports and bootstraps
- clear product-level behavior for `/setup`, `/dashboard/login`, and `/dashboard` when no admin exists

This requirement is about closing those gaps.

---

## Users

| Role | Need |
| --- | --- |
| Platform Admin | Needs to initialize a fresh Minder deployment from the browser without opening a shell inside the container. |
| Platform Admin | Needs a safe recovery path when the admin API key is lost. |
| Developer / MCP Client | Needs to configure Codex, Claude Desktop, Copilot-style clients, or stdio integrations with a single `client_api_key`, without custom token exchange glue. |

---

## User Stories

### Story 1: First-Time Setup Wizard

**As an** Admin deploying Minder for the first time  
**I want to** be redirected to a one-time setup flow when no admin exists  
**So that** I can create the initial admin identity from the dashboard instead of using `docker exec`.

**Acceptance Criteria**:

```gherkin
Given the system has no admin users
When a browser opens /dashboard or /dashboard/login
Then the browser is redirected to /setup
And the /setup page renders a first-run admin creation form
And the form collects email, username, and display name
And on successful submission the system creates the first admin account
And the system returns or displays the bootstrap admin API key exactly once
And the browser is redirected to a one-time setup-complete screen after setup succeeds
And that setup-complete screen reveals the bootstrap admin API key exactly once
And any later request to /setup is rejected or redirected once an admin already exists
```

### Story 2: Admin Access Recovery via CLI

**As an** Admin who lost the dashboard bootstrap API key  
**I want to** rotate or reset admin access from inside the container using a supported command  
**So that** I can recover dashboard access without editing the database manually.

**Acceptance Criteria**:

```gherkin
Given the operator has container exec access
When they run a supported recovery command such as uv run python scripts/reset_admin_api_key.py --username admin
Then the command rotates the admin API key securely
And the new key is printed exactly once
And previously issued admin API keys for that target admin are no longer valid
And the action is recorded in audit history
```

### Story 3: Direct MCP Client Auth (Plug and Play)

**As a** Developer configuring Codex, Claude Desktop, or a Copilot-style MCP client  
**I want to** use the `client_api_key` directly in the MCP client configuration  
**So that** Minder works without an explicit `/v1/auth/token-exchange` pre-step or wrapper script.

**Acceptance Criteria**:

```gherkin
Given an active client_api_key
When the MCP transport receives that key through its supported bootstrap mechanism
Then the gateway validates the raw client_api_key directly
And it resolves a ClientPrincipal for tool execution
And the client can call allowed tools without first calling /v1/auth/token-exchange
And the old token-exchange flow remains available for clients that prefer short-lived bearer tokens
```

### Story 4: Transport Parity for Direct Client Auth

**As a** platform operator  
**I want** direct `client_api_key` authentication to behave consistently across supported transports  
**So that** docs and onboarding templates do not diverge by transport.

**Acceptance Criteria**:

```gherkin
Given a valid client_api_key
When the client uses SSE with X-Minder-Client-Key
Then authenticated tool calls succeed under a ClientPrincipal

Given a valid client_api_key
When the client uses stdio with the documented `MINDER_CLIENT_API_KEY` environment variable
Then authenticated tool calls succeed under a ClientPrincipal

Given an invalid or revoked client_api_key
When any supported transport uses it
Then authentication fails consistently
And the request is rejected with an auth error
```

---

## Scope

### In Scope (v1)

- One-time `/setup` route and server-rendered setup form
- first-admin creation flow for a clean deployment
- CLI recovery command for rotating/resetting admin API-key access
- direct raw `client_api_key` support as a first-class documented auth mode
- stdio parity for direct client auth
- route behavior contract for `/setup`, `/dashboard/login`, and `/dashboard`
- audit logging for setup and admin recovery actions
- documentation and onboarding template updates

### Out of Scope

- Username/password auth for admins
- OAuth / SSO integration
- full multi-admin invitation or approval workflow
- Terraform, Helm, or infrastructure auto-provisioning
- removal of `/v1/auth/token-exchange`

---

## Edge Cases and Error Handling

| Scenario | Expected Behavior |
| --- | --- |
| Two operators race to create the first admin | Only one creation succeeds; the second sees setup already completed. |
| `/setup` is visited after an admin exists | Redirect to `/dashboard/login` or return a clear setup-complete response. |
| Recovery command targets a missing user | Exit non-zero with a clear message; do not mutate anything. |
| Recovery command targets a non-admin user | Refuse the operation explicitly. |
| Revoked client key is used on SSE or stdio | Reject auth consistently. |
| Direct client auth and bearer auth are both supplied | Define deterministic precedence; requirement default is explicit bearer header wins only for admin/user flows, direct client key wins only when client auth is intended. |

---

## Integration Points

| System / Module | Dependency Type | Notes |
| --- | --- | --- |
| `src/minder/server.py` | HTTP/Admin Surface | Must add `/setup` routes and first-run redirect logic. |
| `src/minder/auth/service.py` | Auth Domain | Needs first-admin creation guardrails and admin access recovery support. |
| `src/minder/transport/base.py` | MCP Transport Core | Must continue to support principal resolution from raw client keys. |
| `src/minder/transport/sse.py` | SSE Transport | Already has `X-Minder-Client-Key` support; requirements should preserve and harden it. |
| `src/minder/transport/stdio.py` | Stdio Transport | Needs documented direct-key bootstrap parity. |
| `scripts/` | Operator CLI | Needs a supported recovery script for admin key rotation/reset. |
| `docs/guides/` | Documentation | Must reflect setup flow, browser login, and direct client auth behavior. |

---

## Non-Functional Requirements

- **Security**: admin bootstrap key and rotated recovery keys must be shown exactly once and never stored in plaintext.
- **Idempotence**: `/setup` must become inert once an admin exists.
- **Backward Compatibility**: existing token exchange and bearer-based admin APIs must continue to work.
- **Operator UX**: first-run setup should be completable from a browser in under 2 minutes on a fresh Docker deployment.

---

## Open Questions

- [ ] Should admin recovery rotate only the API key, or also invalidate active dashboard cookies/JWT sessions?
- [ ] Should `/setup` require a deployment bootstrap secret in addition to “no admin exists”, or is “first admin wins” acceptable for the initial local/self-hosted target?

## Implementation Status

The current codebase now implements this requirement set:

- browser-first initial admin setup through `/setup`
- one-time setup completion screen that shows the bootstrap admin API key
- browser admin login at `/dashboard/login`
- CLI admin API-key recovery through `scripts/reset_admin_api_key.py`
- direct `X-Minder-Client-Key` auth for `SSE`
- direct `MINDER_CLIENT_API_KEY` auth for `stdio`
- end-to-end verification in `tests/integration/test_phase4_1_gate.py`

---

## Decisions Log

| Date | Decision | Rationale |
| --- | --- | --- |
| 2026-04-08 | Keep admin auth API-key based instead of introducing passwords | The current system already uses API keys as the primary admin credential; adding passwords would create a second auth model and widen scope unnecessarily. |
| 2026-04-08 | Keep `/v1/auth/token-exchange` even after direct client auth | Short-lived tokens still matter for some clients and future policy controls. |
| 2026-04-08 | Treat SSE direct client auth as baseline, not new scope | The codebase already supports `X-Minder-Client-Key`; the remaining work is parity, hardening, and productization. |
| 2026-04-08 | Use `MINDER_CLIENT_API_KEY` as the canonical stdio bootstrap mechanism | Environment-based bootstrap is the simplest cross-client path for local stdio integrations and keeps the transport contract explicit. |
