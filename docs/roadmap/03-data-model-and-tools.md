# 03. Data Model and MCP Tool Surface

> **Version**: 3.0 — 2026-06-09
> Audited against the live codebase. 26 tools are registered and active in transport.
> Tools removed from MCP registration retain their underlying service methods for HTTP admin use.

---

## Data and Memory Stores

### Skill Store

| Field               | Type        | Description                                      |
| ------------------- | ----------- | ------------------------------------------------ |
| `id`                | UUID        | Primary key                                      |
| `title`             | string      | Skill title                                      |
| `content`           | text        | Code snippet, API usage, pattern, or guidance    |
| `language`          | string      | Programming language                             |
| `tags`              | string[]    | Classification labels                            |
| `workflow_steps`    | string[]    | Workflow steps where the skill is most relevant  |
| `artifact_types`    | string[]    | Artifact types the skill helps produce           |
| `provenance`        | string      | Source identifier (e.g. `phase_4_4`, `git_import`) |
| `quality_score`     | float       | Feedback-derived quality score (0.0–1.0)         |
| `deprecated`        | boolean     | Whether this skill is retired from recall        |
| `source.provider`   | string      | `github`, `gitlab`, or `generic_git`             |
| `source.repo_url`   | string      | Remote repository URL                            |
| `source.ref`        | string      | Imported branch, tag, or commit ref              |
| `source.path`       | string      | Path within the repository                       |
| `embedding`         | vector(768) | Dedicated embedding-model vector                 |
| `usage_count`       | int         | Retrieval count                                  |
| `created_at`        | timestamp   | Created time                                     |
| `updated_at`        | timestamp   | Last updated time                                |

### Knowledge Graph Store

`GraphNode` is metadata-first. The graph captures structure and relationships, not source bodies.

| Field        | Type      | Description                                                                                 |
| ------------ | --------- | ------------------------------------------------------------------------------------------- |
| `id`         | UUID      | Primary key                                                                                 |
| `node_type`  | string    | repository, file, function, controller, route, mq_topic, mq_producer, mq_consumer          |
| `name`       | string    | Stable node name                                                                            |
| `metadata`   | jsonb     | Structural metadata: paths, signatures, route patterns, topics, owner, framework            |
| `created_at` | timestamp | Created time                                                                                |

Graph metadata policy:
- store file path, language, symbol names, signatures, route information, and queue flow
- keep dependency and ownership edges explicit in `GraphEdge`
- do not persist full source content in graph metadata by default
- bounded reusable excerpts only when a code fragment is worth keeping

### Session Store

Sessions are the server-side LLM context checkpoint. A session is owned by either a **human admin** (`user_id`) or an **MCP client** (`client_id`). The `name` field enables **cross-environment recovery** — an LLM can find its session from any machine using the same client API key.

| Field             | Type      | Description                                                   |
| ----------------- | --------- | ------------------------------------------------------------- |
| `id`              | UUID      | Session ID (primary key)                                      |
| `user_id`         | UUID?     | FK to user — set for human sessions, null for client sessions |
| `client_id`       | UUID?     | FK to client — set for MCP client sessions, null for human    |
| `name`            | string?   | Optional project slug for cross-environment lookup            |
| `repo_id`         | UUID?     | FK to repository context                                      |
| `project_context` | jsonb     | Repo, branch, open files, and environment                     |
| `active_skills`   | jsonb     | Active skill set at save time                                 |
| `state`           | jsonb     | Arbitrary checkpoint state (task, decisions, next steps)      |
| `ttl`             | int       | Time to live in seconds (default 86400 = 24 h)                |
| `created_at`      | timestamp | Created time                                                  |
| `last_active`     | timestamp | Last activity time                                            |

#### Cross-environment session recovery flow

```
Machine A — create or recover a session:
  minder_session_boot(project_name="my-api", project_context={"repo_path": "/dev/my-api"})
  → { session_id: "a1b2...", session_found: false }

  minder_session_save(session_id="a1b2...", state={task: "...", next_steps: [...]},
                      branch="feat/x", open_files=["src/service.py"])

/compact or machine switch:

Machine B — same client API key:
  minder_session_boot(project_name="my-api")
  → { session_id: "a1b2...", session_found: true, session_summary: {...}, _next_steps: [...] }
```

The `session_id` UUID is stable across environments for the same session. The `name` is the durable human-readable key that survives context resets. Pass `session_id` to `minder_session_boot` to restore a specific session by UUID.

### Other Stores

| Store | Key fields | Purpose |
|-------|-----------|---------|
| **History Store** | `session_id`, `role`, `content`, `tool_calls`, `tokens_used` | Per-session message history |
| **Error Store** | `error_code`, `error_message`, `stack_trace`, `resolution`, `embedding` | Similar-error retrieval |
| **User Store** | `email`, `username`, `api_key_hash`, `role`, `is_active` | User identity and auth |
| **Workflow Store** | `name`, `version`, `steps`, `policies`, `default_for_repo` | Workflow definitions |
| **Repository Context Store** | `repo_name`, `repo_url`, `workflow_id`, `state_path`, `relationships` | Repository registry |
| **Repository Workflow State** | `repo_id`, `session_id`, `current_step`, `completed_steps`, `artifacts` | Per-session workflow position |
| **Document Store** | `title`, `content`, `doc_type`, `source_path`, `embedding` | Ingested documents |

---

## MCP Tools (26 registered)

All tools listed here are registered in the MCP transport and available to authenticated principals. Underlying service methods for unregistered operations (e.g. `minder_session_create`, `minder_session_restore`) remain available via HTTP admin routes.

### Auth Tools

Not grantable to MCP client principals via `tool_scopes`. `minder_auth_whoami` is always available to all authenticated principals; `minder_auth_login` and `minder_auth_exchange_client_key` are available without a principal (bootstrap path).

| Tool | Description |
|------|-------------|
| `minder_auth_login` | Exchange a human admin API key (`mk_...`) for a JWT bearer token |
| `minder_auth_exchange_client_key` | Exchange a client API key (`mkc_...`) for a scoped short-lived access token |
| `minder_auth_whoami` | Return the current principal identity, role, and active scopes |

### Session Tools

All session tools are **always available** to any authenticated principal — no explicit `tool_scopes` grant is required. `minder_session_boot` is the **single entry point** for all session flows; it handles create, find, and restore transparently.

| Tool | Description |
|------|-------------|
| `minder_session_boot` | Create or recover a named session. Pass `project_name` (slug) and optional `project_context`. Pass `session_id` (UUID) to restore a specific session directly. Returns `session_found`, `session_summary`, and `_next_steps` hints. |
| `minder_session_list` | List sessions owned by the calling principal, sorted newest-first |
| `minder_session_save` | Checkpoint task state and active skills. Pass `branch` and `open_files` to update context in the same call — no separate context call needed. |
| `minder_session_summarize` | Generate a structured summary of the current session. Call before `/compact`, long interruptions, or subagent handoff. |
| `minder_session_cleanup` | Delete expired sessions and their history for the calling principal |

### Memory Tools

Memory stores **project-specific facts**: decisions, constraints, confirmed paths/symbols, architectural choices, and past mistakes. For reusable cross-project patterns, use skill tools instead.

| Tool | Description |
|------|-------------|
| `minder_memory_store` | Store a project fact or decision. Pass `memory_id` to update an existing entry (upsert pattern). |
| `minder_memory_recall` | Retrieve memories by semantic similarity. Pass `current_step` to bias results toward the active workflow step. |
| `minder_memory_list` | List all memories for the calling principal |
| `minder_memory_delete` | Delete a memory entry by ID |

### Skill Tools

Skills store **reusable cross-project patterns**: checklists, code templates, workflow conventions, and engineering practices. For project-specific facts, use memory tools instead.

| Tool | Description |
|------|-------------|
| `minder_skill_store` | Store a reusable pattern. Pass `skill_id` to update an existing entry. Pass `deprecated=True` to retire a skill from recall without deleting it. |
| `minder_skill_recall` | Retrieve skills compatible with the current workflow step. Pass `current_step` for step-aware ranking. |
| `minder_skill_list` | List skills, optionally filtered by step, tags, or quality score |
| `minder_skill_delete` | Permanently remove a skill by ID |

### Workflow Tools

| Tool | Description |
|------|-------------|
| `minder_workflow_step` | Return current step, blockers, and instruction envelope. Pass `include_definition=true` to also return the full workflow definition (replaces the old `minder_workflow_get` — call once per session). |
| `minder_workflow_update` | Mark a step complete or attach an artifact. Advances the workflow when all required artifacts are present. |
| `minder_workflow_guard` | Validate whether a requested action is allowed in the current step. **Required before starting any significant action.** Returns `allowed`, `reason`, and `violations`. |

### Search and Graph Tools

| Tool | Description |
|------|-------------|
| `minder_search_code` | Semantic code search by symbol, concept, or pattern. Requires `repo_path`. |
| `minder_search_errors` | Search similar historical errors and their resolutions. Does not require `repo_path`. |
| `minder_search_graph` | Structural graph queries: routes, imports, dependencies, cross-module relationships. |
| `minder_find_impact` | Blast-radius analysis. Pass a symbol, file, or route to find upstream and downstream impact. Call before modifying shared modules. |

### Agent Tools

| Tool | Description |
|------|-------------|
| `minder_agent_list` | List available subagents. Pass `workflow_step` to find agents scoped to the current step. |
| `minder_agent_get` | Load a subagent's full `system_prompt` and `tools` list. Always call before spawning. |
| `minder_agent_store` | Create or update a subagent definition |

---

## MCP Resources

| Resource          | Description                              |
| ----------------- | ---------------------------------------- |
| `minder://skills` | List all skills with title and tags      |
| `minder://repos`  | List repos with workflow state and IDs   |
| `minder://stats`  | Query count, avg latency, error rate     |

## MCP Prompts

| Prompt     | Description                                          |
| ---------- | ---------------------------------------------------- |
| `debug`    | Debugging prompt template with error-store context   |
| `review`   | Code review prompt template with skill-store context |
| `explain`  | Explanation prompt template with document context    |
| `tdd_step` | Prompt template for the current TDD workflow step    |

---

## Tool Design Patterns

### Upsert (create-or-update)

`minder_memory_store` and `minder_skill_store` act as upsert operations:

```python
# Create new
minder_memory_store(title="Auth decision", content="Use JWT for all endpoints", tags=["auth"])

# Update existing (pass memory_id)
minder_memory_store(memory_id="uuid-here", title="Auth decision", content="Updated content", tags=["auth"])

# Retire a skill without deleting
minder_skill_store(skill_id="uuid-here", deprecated=True, ...)
```

### Workflow definition lazy-load

`minder_workflow_step` with `include_definition=true` returns the full workflow definition in one call. Call once at session start to populate the agent's context; subsequent calls without the flag are lightweight.

```python
# First call — get full definition
step = minder_workflow_step(repo_id=..., repo_path=..., include_definition=True)
# step["workflow"]["steps"], step["workflow"]["policies"] are populated

# Subsequent calls — lightweight current-step check
step = minder_workflow_step(repo_id=..., repo_path=...)
```

### Session boot options

```python
# Option A — find or create by project name
minder_session_boot(project_name="my-api--claude", project_context={"repo_path": "/dev/my-api"})

# Option B — restore specific session by UUID (from .minder/agent.json)
minder_session_boot(project_name="my-api--claude", session_id="a1b2c3d4-...")
```

---

## Workflow-Orchestrated Retrieval Contract

When workflow enforcement is enabled for a repository:

- Every retrieval call receives workflow context (`workflow_id`, `current_step`, `required_artifacts`)
- Memory and skill ranking includes step-compatibility scoring
- Session restore includes the latest validated instruction envelope
- LLM synthesis is scoped to the current step and blocked actions
- `minder_workflow_guard` must return `allowed=true` before any significant step action

---

## Configuration Reference

```toml
[server]
name = "minder"
transport = "sse"          # "sse" | "stdio"
host = "0.0.0.0"
port = 8800
log_level = "info"

[auth]
enabled = true
jwt_secret = "${MINDER_JWT_SECRET}"
jwt_expiry_hours = 24
api_key_prefix = "mk_"

[embedding]
provider = "llama_cpp"
llama_cpp_model_repo = "ggml-org/embeddinggemma-300M-GGUF"
llama_cpp_model_file = "*.gguf"
dimensions = 768

[llm]
provider = "llama_cpp"
llama_cpp_model_repo = "ggml-org/gemma-4-E2B-it-GGUF"
llama_cpp_model_file = "*.gguf"
context_length = 32768
temperature = 0.1
# Optional OpenAI fallback:
# openai_api_key = "${OPENAI_API_KEY}"
# openai_model = "gpt-4o-mini"

[retrieval]
top_k = 10
rerank_top_n = 5
similarity_threshold = 0.7
hybrid_alpha = 0.7

[workflow]
enforcement = "strict"
default_workflow = "tdd"
repo_state_dir = ".minder"
block_step_skips = true
```
