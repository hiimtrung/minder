# Requirements: Phase 4.3 Console Clean Architecture and UI Modernization

**Date**: 2026-04-09
**Status**: Proposed
**Author**: BE + FE

---

## Goal

Refactor the current web console implementation out of the one-file `src/minder/server.py` application shape and move the dashboard UI onto a maintainable frontend stack, while keeping the MCP gateway and existing admin/client-management capabilities working during migration.

This phase must:

- remove the current `server.py` concentration of bootstrap, HTTP routes, HTML rendering, auth wiring, dashboard flows, and runtime startup
- enforce clean architecture boundaries for the console/backend surface
- replace the current server-rendered HTML dashboard approach with a stronger UI framework that is easier to maintain as the console grows
- preserve the current client-management feature set during the migration

---

## Current Baseline

The current codebase already provides:

- MCP gateway transport and server bootstrap in `src/minder/server.py`
- browser admin setup and login flows
- browser-native client registry, create-client flow, detail pages, rotate/revoke actions, onboarding snippets, recent activity, and connection test
- backend admin HTTP endpoints under `/v1/admin/*` and `/v1/auth/token-exchange`

The current codebase still has architectural issues:

- `src/minder/server.py` mixes:
  - application bootstrap
  - dependency wiring
  - dashboard HTTP routes
  - HTML rendering
  - auth/session cookie concerns
  - route/controller logic
  - operational startup logging
- dashboard UI is handwritten HTML-in-Python, which is fast for bootstrap but poor for long-term maintainability
- console behavior is not yet shaped around explicit use cases and controller boundaries

---

## Users

| Role | Need |
| --- | --- |
| Platform Admin | Needs a dashboard that can grow without fragile HTML strings embedded in Python handlers. |
| Backend Engineer | Needs the admin/backend surface to follow clean architecture so it can be changed safely. |
| Frontend Engineer | Needs a modern UI stack with reusable components, typed APIs, and maintainable state management. |

---

## User Stories

### Story 1: Clean Backend Boundaries

**As a** Backend Engineer  
**I want to** separate controllers, use cases, and infrastructure concerns for the console/backend surface  
**So that** the application is maintainable and consistent with clean architecture.

**Acceptance Criteria**:

```gherkin
Given the console/backend refactor is complete
When a dashboard HTTP request is handled
Then the request enters through presentation-layer controllers
And business logic runs in application-layer use cases
And persistence remains behind repository interfaces
And `src/minder/server.py` no longer contains dashboard HTML rendering or large route/controller logic blocks
```

### Story 2: Dedicated Dashboard UI Stack

**As a** Frontend Engineer  
**I want to** build the dashboard on a stronger UI framework than inline HTML in Python  
**So that** the console can evolve into a maintainable admin application.

**Acceptance Criteria**:

```gherkin
Given the new dashboard stack is implemented
When an admin opens the console
Then the UI is served by a dedicated frontend application
And the frontend consumes typed backend APIs instead of inline HTML templates
And the client-management flows remain available during or after migration
```

### Story 3: No Feature Regression During Migration

**As an** Admin  
**I want** the existing setup, login, client management, onboarding, and audit-related flows to keep working while the architecture changes  
**So that** migration does not block actual dashboard usage.

**Acceptance Criteria**:

```gherkin
Given the console migration is in progress
When an admin uses the dashboard
Then setup, login, create client, rotate key, revoke key, onboarding snippets, connection testing, and recent activity continue to work
And the feature set is covered by end-to-end verification
```

---

## Scope

### In Scope (v1)

- extract console/backend concerns out of `src/minder/server.py`
- create explicit presentation/application/infrastructure boundaries for dashboard/backend flows
- introduce a dedicated dashboard frontend stack
- keep current `/v1/admin/*` and auth contracts compatible where possible
- migrate current client-management browser UX onto the new UI stack
- add migration gate to prove no regression

### Out of Scope

- broader Phase 4 observability backend implementation
- workflow/repository/user management features beyond current dashboard scope
- replacing MCP transport stack
- replacing domain models or repository interfaces unrelated to console flows
- hosted multi-tenant portal concerns

---

## Key Architectural Decisions Required

| Topic | Required Decision |
| --- | --- |
| Backend boundary | Split current console/backend logic from `server.py` into presentation + application + bootstrap layers |
| UI framework | Move dashboard UI to `Astro` with `Tailwind CSS` and typed browser scripts/components where needed |
| UI data layer | Use typed HTTP API contracts plus a query/form layer suitable for long-term admin UI maintenance |
| Legacy SSR | Keep only as transitional fallback, then remove once parity is verified |

---

## Recommended UI Stack

The dashboard should move to:

- `Astro`
- `TypeScript`
- `Tailwind CSS`
- lightweight client-side islands only where interactivity is needed
- typed fetch clients and schema validation for admin API integration

Rationale:

- keeps the UI lightweight and easy to ship from a single repository
- avoids a second always-on frontend runtime and extra production port
- still gives maintainable component and styling structure
- is easier to operate than HTML strings embedded in Python

---

## Integration Points

| System / Module | Dependency Type | Notes |
| --- | --- | --- |
| `src/minder/server.py` | Current bootstrap seam | Must be reduced to composition/bootstrap only. |
| `src/minder/auth/service.py` | Application dependency | Existing auth and client-management use cases should be reused rather than rewritten. |
| `src/minder/store/interfaces.py` | Domain boundary | Repository interfaces remain the persistence boundary. |
| `src/minder/transport/` | Gateway/MCP runtime | Must remain intact while admin console moves out. |
| `src/dashboard/` | New frontend app | Astro-based dashboard that replaces Python-rendered HTML console and can be built into static assets. |

---

## Non-Functional Requirements

- **Maintainability**: Console/backend code should be navigable by layer, not by one-file route accumulation.
- **Compatibility**: Existing admin/client-management flows must keep working during migration.
- **Incremental Delivery**: Migration should be wave-based so behavior can be verified without a flag day rewrite.
- **Testability**: New console layers must be covered by backend integration tests and frontend acceptance coverage.

---

## Open Questions

- [ ] Should Astro assets be built as part of the Python image build, or via a separate frontend build step that publishes static assets into the backend image?
- [ ] Should legacy server-rendered routes stay available behind a feature flag during migration, or be removed as soon as parity is reached?
- [ ] Do we want a dedicated dashboard backend package immediately, or first refactor the existing Starlette routes into clean layers and move the frontend separately?

---

## Decisions Log

| Date | Decision | Rationale |
| --- | --- | --- |
| 2026-04-09 | Treat `src/minder/server.py` as a refactor target, not a long-term home for dashboard logic | The file currently violates the desired clean-architecture boundary by mixing composition, controllers, and view rendering. |
| 2026-04-09 | Use `Astro` + `Tailwind CSS` as the target dashboard framework | It keeps the dashboard lightweight, easier to serve from the existing Python app, and more aligned with the desire to avoid a separate frontend runtime/port. |
