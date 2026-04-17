# Phase 4.0 Tracker — Gateway Auth and Dashboard Foundation

**Goal**: make MCP onboarding and client management workable through gateway auth plus the first dashboard surface.

## Status

| Area      | Status | Notes                             |
| --------- | ------ | --------------------------------- |
| Phase 4.0 | `DONE` | End-to-end onboarding gate passed |

## Tasks

| Task          | Owner      | Wave         | Status | Summary                                 | Related Context                                                                                                    |
| ------------- | ---------- | ------------ | ------ | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `P4.0-T01`    | `BE`       | `P4.0-Wave1` | `DONE` | Client registry domain model            | [../design/mcp-gateway-auth-dashboard.md](../design/mcp-gateway-auth-dashboard.md)                                 |
| `P4.0-T02`    | `BE`       | `P4.0-Wave2` | `DONE` | Token exchange API                      | [../design/mcp-gateway-auth-dashboard.md](../design/mcp-gateway-auth-dashboard.md)                                 |
| `P4.0-T03`    | `BE`       | `P4.0-Wave1` | `DONE` | Principal-based gateway auth            | [../design/mcp-gateway-auth-dashboard.md](../design/mcp-gateway-auth-dashboard.md)                                 |
| `P4.0-T04`    | `BE/PE`    | `P4.0-Wave2` | `DONE` | Redis-backed client sessions            | [../system-design.md](../system-design.md)                                                                         |
| `P4.0-T05`    | `FE`       | `P4.0-Wave3` | `DONE` | Dashboard backend for client management | [../design/mcp-gateway-auth-dashboard.md](../design/mcp-gateway-auth-dashboard.md)                                 |
| `P4.0-T06`    | `FE`       | `P4.0-Wave3` | `DONE` | Initial dashboard frontend shell        | [../design/mcp-gateway-auth-dashboard.md](../design/mcp-gateway-auth-dashboard.md)                                 |
| `P4.0-T07`    | `FE`       | `P4.0-Wave3` | `DONE` | MCP onboarding templates                | [../guides/admin-client-onboarding.md](../guides/admin-client-onboarding.md)                                       |
| `P4.0-T08`    | `BE`       | `P4.0-Wave4` | `DONE` | Audit and revocation hardening          | [../requirements/p4_1_dashboard_setup_and_direct_auth.md](../requirements/p4_1_dashboard_setup_and_direct_auth.md) |
| `P4.0-VERIFY` | `BE/FE/PE` | `P4.0-Wave4` | `DONE` | End-to-end client onboarding gate       | [../../tests/e2e/test_phase4_gateway_auth.py](../../tests/e2e/test_phase4_gateway_auth.py)                         |
