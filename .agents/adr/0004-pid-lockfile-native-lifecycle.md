# ADR 0004: Process Lifecycle Management With PID Lockfile In Native Shell

## Status
Accepted

## Context
When the Tauri Desktop application crashes or is force-terminated, the child Python `minder-server` process can become orphaned as a zombie process, holding port 8800 and blocking subsequent app launches.

## Decision
1. Persist the `minder-server` process PID to `~/.minder/minder-server.pid`.
2. On Tauri startup: If port 8800 is occupied, read the PID file and terminate the stale process before spawning a new instance.
3. On Tauri exit: Send `SIGTERM` with a 3s graceful timeout, falling back to `SIGKILL`.

## Consequences
- Eliminates port 8800 collisions and zombie processes completely.
