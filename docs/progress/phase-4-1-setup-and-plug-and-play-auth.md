# Phase 4.1 Tracker — Setup and Plug-and-Play Auth

**Goal**: remove manual setup friction and make direct client key auth work for static MCP clients.

## Status

| Area      | Status | Notes                                                     |
| --------- | ------ | --------------------------------------------------------- |
| Phase 4.1 | `DONE` | Setup wizard, recovery, and direct key auth all delivered |

## Tasks

| Task          | Owner   | Wave         | Status | Summary                                      | Related Context                                                                                                                                                                                                |
| ------------- | ------- | ------------ | ------ | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `P4.1-T01`    | `FE/BE` | `P4.1-Wave1` | `DONE` | First-time setup wizard                      | [../requirements/p4_1_dashboard_setup_and_direct_auth.md](../requirements/p4_1_dashboard_setup_and_direct_auth.md)                                                                                             |
| `P4.1-T02`    | `PE`    | `P4.1-Wave2` | `DONE` | CLI admin API-key recovery                   | [../requirements/p4_1_dashboard_setup_and_direct_auth.md](../requirements/p4_1_dashboard_setup_and_direct_auth.md)                                                                                             |
| `P4.1-T03`    | `BE`    | `P4.1-Wave3` | `DONE` | Direct client API-key auth for SSE and stdio | [../requirements/p4_1_dashboard_setup_and_direct_auth.md](../requirements/p4_1_dashboard_setup_and_direct_auth.md)                                                                                             |
| `P4.1-VERIFY` | `BE/FE` | `P4.1-Wave4` | `DONE` | Plug-and-play acceptance gate                | [../../tests/integration/test_phase4_1_setup_wizard.py](../../tests/integration/test_phase4_1_setup_wizard.py); [../../tests/integration/test_phase4_1_gate.py](../../tests/integration/test_phase4_1_gate.py) |
