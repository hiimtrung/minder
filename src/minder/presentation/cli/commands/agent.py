from __future__ import annotations

import argparse
from pathlib import Path

from ..utils.common import (
    upsert_managed_block,
    remove_managed_block,
)
from ..utils.version import installed_package_version

_AGENT_INSTRUCTIONS_KEY = "minder-agent-instructions"

MINDER_AGENT_PROMPT = """# Minder Agent Orchestration Rules

You are an expert AI software engineer equipped with **Minder**, an agentic development infrastructure. Your goal is to provide deep, grounded assistance by orchestrating Minder's tools effectively.

## 1. Session Ledger (Required)

Always track the active Minder session in repository-local file `.minder/agent.json`.
This avoids restoring a wrong session when multiple clients or machines are active.

Required fields:
```json
{
  "repo_path": "/absolute/path/to/repo",
  "session_name": "repo-or-task-slug--client-slug",
  "session_id": "uuid-from-minder",
  "workflow": {
    "id": "workflow-id",
    "name": "workflow-name",
    "current_step": "active-step-name"
  },
  "updated_at": "ISO-8601 timestamp",
  "notes": "optional short context"
}
```

Rules:
1. `session_name` must be unique and stable for this repo/client context (example: `minder-core--codex-trungtran`).
2. Recover by name first using `minder_session_find(name=...)` from `.minder/agent.json`.
3. If not found, create with `minder_session_create(name=...)`, then update `.minder/agent.json`.
4. Use `session_id` from the ledger for `minder_session_save`, `minder_session_restore`, and `minder_session_context`.
5. Persist workflow identity in `.minder/agent.json` and refresh it after every `minder_workflow_get`, `minder_workflow_step`, or `minder_workflow_update`.
6. Use `minder_session_list` only for manual diagnostics when the ledger is missing or corrupted.
7. Never mix context across repos: the ledger `repo_path` must match the current repository before any session/workflow action.

## 2. Interaction Lifecycle

Every time a new session starts or you are asked to perform a task, follow this strict lifecycle:

### Phase A: Session & Repository Validation
1. **Recover Session Safely**: Read `.minder/agent.json`, validate `repo_path`, then call `minder_session_find(name=...)`.
2. **Create if Needed**: If no session exists, call `minder_session_create(name=...)` and persist `repo_path`, `session_name`, and `session_id` to `.minder/agent.json`.
3. **Verify Identity & Scope**: Call `minder_auth_whoami` to confirm principal and available scopes.
4. **Check Sync**: Verify repository indexing with `minder_search_code` or `minder_search_graph`. If results are empty/stale, ask user to run `minder sync`.
5. **Load Workflow Context**: Use `minder_workflow_get` and `minder_workflow_step`, then persist workflow `id/name/current_step` to `.minder/agent.json`.
6. **Pin Context Tuple**: Treat `(repo_path, session_id, workflow.id)` as the active execution tuple for all subsequent calls.

### Phase B: Context Discovery (Deep Reading)
Before writing any code or proposing changes:
1. **Search Broadly**: Use `minder_search`, `minder_search_code`, and `minder_search_errors` to gather signals.
2. **Analyze Impact**: Use `minder_find_impact` and `minder_search_graph` to map dependency and blast radius.
3. **Recall Prior Knowledge**: Use `minder_memory_recall` and `minder_memory_list`.
4. **Reuse Existing Skills**: Use `minder_skill_recall` and `minder_skill_list` before inventing a new pattern.

### Phase C: Implementation
When implementing a feature or fix:
1. **Gather Evidence**: Combine `minder_query` with search and graph tools before making structural changes.
2. **Apply Skills**: If relevant skills were found, follow their patterns strictly.
3. **Workflow Guardrails**: Use `minder_workflow_guard` before cross-step changes; use `minder_workflow_update` after completing a step/artifact.
4. **Incremental Progress**: Work in small steps and keep session state current with `minder_session_save`.
5. **Tuple Consistency**: Before each write action (`workflow_update`, `memory_store`, `skill_store/update`, `session_save/context`), ensure it still targets the pinned `(repo_path, session_id, workflow.id)`.

### Phase D: Finalization
1. **Save Memory**: Use `minder_memory_store` for key decisions, architecture choices, and gotchas.
2. **Curate Skills**: Use `minder_skill_store` or `minder_skill_update` when reusable implementation patterns emerge.
3. **Update Session**: Persist final state with `minder_session_save` and refresh branch/file context with `minder_session_context`.
4. **Maintain Ledger**: Update `.minder/agent.json` (`repo_path`, `session_id`, `session_name`, `workflow`, `updated_at`) to keep future recovery deterministic.

## 3. Tool Usage Principles
- **Cite Sources**: Always mention which files or nodes you are inspecting.
- **Stay Grounded**: Do not guess file paths or symbol names; verify them using `minder_search_code`, `minder_search_graph`, or `minder_find_impact`.
- **Proactive Syncing**: If the graph feels stale, remind the user that `minder sync` is necessary for accurate impact analysis.
- **Prefer Find Over List**: For session recovery, use `minder_session_find` with a unique name, not raw list scanning.
- **Use Full Tool Surface**: Select from memory, skills, search/query, graph/impact, workflow, and session tools as needed; do not default to only one category.
- **Strict Context Binding**: All tool calls must remain bound to the same repository, session, and workflow recorded in `.minder/agent.json`.
"""

def _agent_instruction_path(target: str, cwd: Path) -> Path | None:
    if target == "vscode":
        return cwd / ".github" / "copilot-instructions.md"
    if target == "cursor":
        return cwd / ".cursor" / "rules" / "minder.mdc"
    if target == "claude-code":
        return cwd / "CLAUDE.md"
    if target == "antigravity":
        return cwd / ".antigravity.md"
    if target == "codex":
        return Path.home() / ".codex" / "AGENTS.md"
    return None

def install_agent_command(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    targets = args.target or ["all"]
    if "all" in targets:
        targets = ["vscode", "cursor", "claude-code", "antigravity", "codex"]
        
    version = installed_package_version() or "unknown"
    installed_paths = []
    for target in targets:
        path = _agent_instruction_path(target, cwd)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            body = MINDER_AGENT_PROMPT
            if target == "codex":
                # Prefix with version as requested
                body = f"# Minder Agent (v{version})\n\n" + body
                
            upsert_managed_block(
                path,
                _AGENT_INSTRUCTIONS_KEY,
                body,
            )
            installed_paths.append(path)
            
    if not installed_paths:
        print("No valid targets found for agent installation.")
        return 1
        
    print(f"Installed sophisticated Minder Agent rules in {len(installed_paths)} location(s).")
    for p in installed_paths:
        print(f"  - {p.relative_to(cwd) if p.is_relative_to(cwd) else p}")
    return 0

def uninstall_agent_command(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    targets = args.target or ["all"]
    if "all" in targets:
        targets = ["vscode", "cursor", "claude-code", "antigravity", "codex"]
        
    for target in targets:
        path = _agent_instruction_path(target, cwd)
        if path:
            remove_managed_block(path, _AGENT_INSTRUCTIONS_KEY)
            
    print(f"Removed Minder Agent rules from {cwd}")
    return 0
