# Phase 8 Tracker — Agent Intelligence and Self-Correction

**Goal**: close the gaps identified in the 2026-04-28 RAG agent audit. Minder already has solid
workflow tracking and LLM drift-prevention; this phase adds the missing self-correction loop —
letting the agent fix its own memories and skills, summarise session work automatically, generate
smart clarifying questions, and give the LLM richer guidance on when and how to use each tool.

**Audit source**: conversation on 2026-04-28 — full feature-by-feature findings recorded below.

---

## Audit Findings (2026-04-28)

### Already fully implemented — no work needed

| Feature | Evidence |
|---|---|
| Workflow definition + step-state persistence | `models/workflow.py`, `models/repository.py` (WorkflowState), `tools/workflow.py` (4 MCP tools), `continuity.py:102` (instruction_envelope) |
| LLM goal-drift prevention | `graph/nodes/guard.py` (output contract validation, unsafe-pattern scan), `graph/nodes/reasoning.py` (instruction_envelope + continuity_brief injection), prompt template `{correction_required}` retry loop |

### Gaps that need work

| ID | Feature | Status | Gap severity | Key finding |
|---|---|---|---|---|
| `P8-G1` | Memory correction via MCP | Partial | **HIGH** | HTTP admin `update_memory` exists (`presentation/http/admin/memories.py:123`) but no `minder_memory_update` MCP tool; LLM cannot fix wrong memories conversationally |
| `P8-G2` | Skill deprecated flag | Partial | MEDIUM | `minder_skill_update` supports `quality_score` but no `deprecated: bool` field; outdated skills still surface in recall |
| `P8-G3` | Session work auto-summary | Partial | MEDIUM | `build_continuity_brief()` reconstructs task/blockers from stored state (`continuity.py:134`) but no `minder_session_summarize` MCP tool; LLM cannot request a structured summary |
| `P8-G4` | Tool usage guidance | Partial | MEDIUM | `tool_capability_manifest()` lists tool names by category (`tools/registry.py:228`) but descriptions are one-liners with no "when to use", usage patterns, or lifecycle examples |
| `P8-G5` | Smart clarifying questions | None | CRITICAL | Zero implementation; no node generates questions to user; no confirmation loop before memory/skill/workflow corrections |

---

## Status

| Area | Status | Notes |
|---|---|---|
| Phase 8 | `DONE` | All 5 tasks implemented and verified; 26/26 tests pass |
| Sprint 1 — Foundation corrections | `DONE` | P8-T01, P8-T02 shipped |
| Sprint 2 — Session intelligence | `DONE` | P8-T03, P8-T04 shipped |
| Sprint 3 — Clarification UX | `DONE` | P8-T05 shipped |

---

## Tasks

### Sprint 1 — Foundation corrections

| Task | Owner | Status | Summary | Acceptance criteria |
|---|---|---|---|---|
| `P8-T01` | `BE` | `DONE` | **`minder_memory_update` MCP tool** — expose memory correction to LLM. Add `update_memory()` to `tools/memory.py`, register in `tools/registry.py` and `bootstrap/transport.py`. Reuses `ISkillRepository.update_skill()` already present in `store/interfaces.py`. Re-embeds on title/content change. | Tool callable from MCP client; updates title/content/tags; embedding recalculated when content changes; audit log written |
| `P8-T02` | `BE` | `DONE` | **Skill `deprecated` flag** — add `deprecated: bool = False` to `models/skill.py` and `Skill` DB schema. Add `deprecated` param to `minder_skill_update` in `tools/skills.py`. Filter `deprecated=True` skills out of `minder_skill_recall` and `minder_skill_list` (unless `include_deprecated=True` passed). Add migration. | `deprecated=True` skills absent from default recall; `minder_skill_update(skill_id, deprecated=True)` works end-to-end |

### Sprint 2 — Session intelligence

| Task | Owner | Status | Summary | Acceptance criteria |
|---|---|---|---|---|
| `P8-T03` | `BE` | `DONE` | **`minder_session_summarize` MCP tool** — auto-generate structured work summary for current session. Calls `build_continuity_brief()` (already in `continuity.py:134`) and optionally enriches with LLM via `ContinuitySynthesizer` pattern. Returns: `task`, `completed`, `blockers`, `next_actions`, `open_files`, `active_skills`. Stores result back into `session.state["summary"]` so it survives context compaction. | Tool returns structured JSON summary; `session.state["summary"]` updated; works without LLM (heuristic fallback) |
| `P8-T04` | `BE` | `DONE` | **Enriched tool usage guidance** — expand `TOOL_DESCRIPTIONS` in `tools/registry.py` with "when to use" annotations and usage patterns. Add a `TOOL_USAGE_PATTERNS` dict covering: memory vs skill store decision, lifecycle (create → use → update → compact/deprecate), workflow guard before step transitions, session summarize before long context. Inject patterns into `tool_capability_manifest()` so they reach the LLM prompt via `ReasoningNode`. | `tool_capability_manifest()` includes patterns; LLM prompt contains usage guidance; no regression on existing prompt size budget |

### Sprint 3 — Clarification UX

| Task | Owner | Status | Summary | Acceptance criteria |
|---|---|---|---|---|
| `P8-T05` | `BE/ML` | `DONE` | **`ClarificationNode` in graph pipeline** — new graph node that detects ambiguous or correction-intent queries (memory fix, skill update, workflow override) and generates 2–3 structured options for the user to choose from before the LLM acts. Insert between `PlanningNode` and `ReasoningNode` when plan intent is `"correct"` or `"update"`. Uses lightweight heuristic classification first; falls back to LLM generation. | Ambiguous correction queries trigger clarification options; non-ambiguous queries pass through unaffected; options cover memory/skill/workflow correction paths |

### Verification

| Task | Owner | Status | Summary |
|---|---|---|---|
| `P8-VERIFY` | `BE` | `DONE` | Acceptance gate: `tests/integration/test_agent_self_correction.py` — 26/26 tests pass; covers memory update round-trip, skill deprecated filter, session summary content, tool manifest patterns, clarification trigger on correction-intent query |

---

## Implementation notes

### P8-T01 — Memory update MCP tool
The store layer already supports updates via `ISkillRepository.update_skill(**kwargs)`.
The HTTP admin endpoint at `presentation/http/admin/memories.py:123` shows the exact
embedding-recalculation pattern to reuse. The MCP tool should accept:
`(memory_id, *, title=None, content=None, tags=None)` — all optional, only changed fields written.

### P8-T02 — Skill deprecated flag
Migration note: existing `Skill` rows default to `deprecated=False`. The MongoDB store
(`store/mongodb/operational_store.py`) uses dict projection so adding the field with a default
is backwards-compatible without a migration script; the relational store needs an `ALTER TABLE`.
The `minder_skill_recall` blended score already weights `quality_score`; `deprecated=True` should
be a hard filter (exclude entirely) not a score penalty.

### P8-T03 — Session summarize tool
`build_continuity_brief()` in `continuity.py:134` already extracts `task`, `blockers`,
`next_valid_actions`, `confirmed_progress` from `session.state + workflow_state`. The MCP tool
wrapper is thin: load session → call `build_continuity_brief()` → optionally call LiteRT via
`ContinuitySynthesizer` for richer prose → store back into `session.state["summary"]`.
The LiteRT call is optional; if runtime is `"mock"`, the heuristic brief is returned as-is.

### P8-T04 — Tool usage guidance
New `TOOL_USAGE_PATTERNS` constant in `tools/registry.py`. Format: dict keyed by tool name,
value is a short "use when:" string. `tool_capability_manifest()` appends a `"usage_patterns"`
section. Keep total manifest under 800 chars to avoid prompt bloat — use one-line patterns only.

### P8-T05 — ClarificationNode
Trigger condition: `state.plan["intent"]` is `"correct"` / `"update"` / `"delete"` AND
`state.metadata.get("clarification_done")` is falsy. Generate 2–3 options as structured JSON
in `state.clarification_options`. The SSE transport yields a `{"type": "clarification", ...}`
event; the dashboard chat shell renders as a choice list. On next user turn the selected option
is injected into `state.metadata["clarification_done"] = True` to skip re-triggering.

---

## Dependencies

| This task | Depends on |
|---|---|
| `P8-T01` | `store/interfaces.py` `update_skill()` (exists), `tools/memory.py` (exists) |
| `P8-T02` | `models/skill.py` schema change — must land before `P8-T04` tool manifest update |
| `P8-T03` | `continuity.py:build_continuity_brief()` (exists), `ContinuitySynthesizer` (exists) |
| `P8-T04` | `P8-T02` (deprecated field must exist before patterns reference it) |
| `P8-T05` | `P8-T01`, `P8-T02`, `P8-T03` — clarification options need the corrective tools to exist |
| `P8-VERIFY` | All P8-T tasks |
