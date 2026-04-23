# 03. Data Model and MCP Tool Surface

> **Version**: 2.0 — 2026-04-15
> Audited against the live codebase. Each tool table notes whether the tool is
> **Implemented** (live in transport), **Partial** (code exists but not registered),
> or **Planned** (spec only, not yet built).

---

## Data and Memory Stores

### Skill Store

| Field           | Type        | Description                                   |
| --------------- | ----------- | --------------------------------------------- |
| `id`            | UUID        | Primary key                                   |
| `title`         | string      | Skill title                                   |
| `content`       | text        | Code snippet, API usage, pattern, or guidance |
| `language`      | string      | Programming language                          |
| `tags`          | string[]    | Classification labels                         |
| `embedding`     | vector(768) | Dedicated embedding-model vector              |
| `usage_count`   | int         | Retrieval count                               |
| `quality_score` | float       | Feedback-derived quality score                |
| `created_at`    | timestamp   | Created time                                  |
| `updated_at`    | timestamp   | Last updated time                             |

### Planned Skill Catalog Extensions

The live store is intentionally minimal today. The planned skill-catalog expansion adds provenance and workflow-aware curation fields without changing the core role of the skill store.

| Field               | Type     | Description                                      |
| ------------------- | -------- | ------------------------------------------------ |
| `workflow_steps`    | string[] | Workflow steps where the skill is most relevant  |
| `source.provider`   | string   | `github`, `gitlab`, or `generic_git`             |
| `source.repo_url`   | string   | Remote repository URL                            |
| `source.ref`        | string   | Imported branch, tag, or commit ref              |
| `source.path`       | string   | Path within the repository                       |
| `source.commit_sha` | string   | Commit imported from when available              |
| `excerpt_kind`      | string   | `none` or `reusable_excerpt`                     |
| `curation_status`   | string   | `draft`, `imported`, `reviewed`, or `deprecated` |

### Knowledge Graph Store

`GraphNode` must remain metadata-first. The graph is intended to capture structure and relationships, not to duplicate raw source files.

| Field        | Type      | Description                                                                                 |
| ------------ | --------- | ------------------------------------------------------------------------------------------- |
| `id`         | UUID      | Primary key                                                                                 |
| `node_type`  | string    | repository, file, function, controller, route, mq_topic, mq_producer, mq_consumer           |
| `name`       | string    | Stable node name                                                                            |
| `metadata`   | jsonb     | Structural metadata such as paths, signatures, route patterns, topics, owner, and framework |
| `created_at` | timestamp | Created time                                                                                |

Graph metadata policy:

- store file path, language, symbol names, signatures, route information, and queue flow
- keep dependency and ownership edges explicit in `GraphEdge`
- do not persist full source content in graph metadata by default
- if a code fragment is retained, store a bounded reusable excerpt outside the default graph payload

Planned ingestion direction:

- prefer repo-local extraction through `minder-cli` over slow server-centric broad scans
- use `git diff` to drive delta refresh by default
- send structural JSON to the server sync API while keeping the server as the system of record

### History Store

| Field             | Type      | Description                         |
| ----------------- | --------- | ----------------------------------- |
| `id`              | UUID      | Primary key                         |
| `session_id`      | UUID      | FK to session                       |
| `role`            | enum      | user, assistant, system, tool       |
| `content`         | text      | Message content                     |
| `reasoning_trace` | text      | Reasoning summary or trace metadata |
| `tool_calls`      | jsonb     | Tool invocation records             |
| `tokens_used`     | int       | Token count                         |
| `latency_ms`      | int       | Response time                       |
| `created_at`      | timestamp | Created time                        |

### Error Store

| Field           | Type        | Description                           |
| --------------- | ----------- | ------------------------------------- |
| `id`            | UUID        | Primary key                           |
| `error_code`    | string      | Standardized error code               |
| `error_message` | text        | Original message                      |
| `stack_trace`   | text        | Stack trace                           |
| `context`       | jsonb       | Query, input, state, and tool context |
| `resolution`    | text        | Known resolution if available         |
| `embedding`     | vector(768) | Similar-error retrieval embedding     |
| `resolved`      | boolean     | Resolution status                     |
| `created_at`    | timestamp   | Created time                          |

### User Store

| Field          | Type      | Description                         |
| -------------- | --------- | ----------------------------------- |
| `id`           | UUID      | Primary key                         |
| `email`        | string    | Unique email                        |
| `username`     | string    | Git username or configured username |
| `display_name` | string    | Display name                        |
| `api_key_hash` | string    | Bcrypt hash of API key              |
| `role`         | enum      | admin, member, readonly             |
| `settings`     | jsonb     | User preferences                    |
| `is_active`    | boolean   | Active status                       |
| `created_at`   | timestamp | Created time                        |
| `last_login`   | timestamp | Last login time                     |

### Session Store

Sessions are the server-side LLM context checkpoint. A session is owned by
either a **human admin** (`user_id`) or an **MCP client** (`client_id`). The
`name` field enables **cross-environment recovery** — an LLM can find its session
from any machine using the same client API key without remembering the UUID.

| Field             | Type      | Description                                                   |
| ----------------- | --------- | ------------------------------------------------------------- |
| `id`              | UUID      | Session ID (primary key)                                      |
| `user_id`         | UUID?     | FK to user — set for human sessions, null for client sessions |
| `client_id`       | UUID?     | FK to client — set for MCP client sessions, null for human    |
| `name`            | string?   | Optional project label for cross-environment lookup           |
| `repo_id`         | UUID?     | FK to repository context                                      |
| `project_context` | jsonb     | Repo, branch, open files, and environment                     |
| `active_skills`   | jsonb     | Active skill set at save time                                 |
| `state`           | jsonb     | Arbitrary checkpoint state (task, decisions, next steps)      |
| `ttl`             | int       | Time to live in seconds (default 86400 = 24 h)                |
| `created_at`      | timestamp | Created time                                                  |
| `last_active`     | timestamp | Last activity time                                            |

#### Cross-environment session recovery flow

```
Machine A (same client API key):
  minder_session_create(name="omi-channel-phase5") → {session_id: "a1b2..."}
  minder_session_save(session_id, state={task: "...", next_steps: [...]})

/compact or machine switch:

Machine B (same client API key):
  minder_session_find(name="omi-channel-phase5")
  → {session_id: "a1b2...", state: {...}, project_context: {...}}
  → LLM resumes with full context
```

The `session_id` UUID is stable across environments for the same session.
The `name` is the durable human-readable key that survives context resets.

### Metadata Store

| Field         | Type      | Description                                  |
| ------------- | --------- | -------------------------------------------- |
| `id`          | UUID      | Primary key                                  |
| `entity_type` | string    | skill, history, error, document, or workflow |
| `entity_id`   | UUID      | Related entity ID                            |
| `key`         | string    | Metadata key                                 |
| `value`       | jsonb     | Metadata value                               |
| `source`      | string    | user, system, or import                      |
| `version`     | int       | Schema version                               |
| `created_at`  | timestamp | Created time                                 |

### Document Store

| Field         | Type        | Description                         |
| ------------- | ----------- | ----------------------------------- |
| `id`          | UUID        | Primary key                         |
| `title`       | string      | Document title                      |
| `content`     | text        | Raw content                         |
| `doc_type`    | enum        | markdown, code, api_spec, or config |
| `source_path` | string      | Original source path                |
| `chunks`      | jsonb       | Chunked content with offsets        |
| `embedding`   | vector(768) | Document-level embedding            |
| `project`     | string      | Project or repository name          |
| `created_at`  | timestamp   | Import time                         |
| `updated_at`  | timestamp   | Last sync time                      |

### Rule Store

| Field         | Type      | Description                              |
| ------------- | --------- | ---------------------------------------- |
| `id`          | UUID      | Primary key                              |
| `title`       | string    | Rule name                                |
| `description` | text      | Description of the rule                  |
| `pattern`     | string    | Glob or regex matcher                    |
| `content`     | text      | Rule body                                |
| `priority`    | int       | Execution priority                       |
| `scope`       | enum      | global, project, language, or repository |
| `active`      | boolean   | Enabled or disabled                      |
| `created_at`  | timestamp | Created time                             |

### Feedback Store

| Field           | Type      | Description                             |
| --------------- | --------- | --------------------------------------- |
| `id`            | UUID      | Primary key                             |
| `entity_type`   | string    | skill, response, retrieval, or workflow |
| `entity_id`     | UUID      | Related entity ID                       |
| `rating`        | int       | Rating from 1 to 5                      |
| `feedback_text` | text      | Optional free-form feedback             |
| `context`       | jsonb     | Query, task, or workflow context        |
| `created_at`    | timestamp | Created time                            |

### Workflow Store

| Field              | Type      | Description                               |
| ------------------ | --------- | ----------------------------------------- |
| `id`               | UUID      | Primary key                               |
| `name`             | string    | Workflow name                             |
| `version`          | int       | Workflow version                          |
| `steps`            | jsonb     | Ordered step definitions                  |
| `policies`         | jsonb     | Required gates, blockers, and permissions |
| `default_for_repo` | boolean   | Whether it is the default workflow        |
| `created_at`       | timestamp | Created time                              |
| `updated_at`       | timestamp | Last updated time                         |

### Repository Context Store

| Field              | Type      | Description                                    |
| ------------------ | --------- | ---------------------------------------------- |
| `id`               | UUID      | Primary key                                    |
| `repo_name`        | string    | Repository name                                |
| `repo_url`         | string    | Remote URL                                     |
| `default_branch`   | string    | Default branch                                 |
| `workflow_id`      | UUID      | FK to workflow                                 |
| `state_path`       | string    | Path inside repo for local state files         |
| `context_snapshot` | jsonb     | Latest repo summary and context                |
| `relationships`    | jsonb     | Modules, services, ownership, and dependencies |
| `created_at`       | timestamp | Created time                                   |
| `updated_at`       | timestamp | Last updated time                              |

### Repository Workflow State Store

| Field             | Type      | Description                               |
| ----------------- | --------- | ----------------------------------------- |
| `id`              | UUID      | Primary key                               |
| `repo_id`         | UUID      | FK to repository context                  |
| `session_id`      | UUID      | FK to session                             |
| `current_step`    | string    | Current workflow step                     |
| `completed_steps` | jsonb     | Completed steps                           |
| `blocked_by`      | jsonb     | Blocking conditions                       |
| `artifacts`       | jsonb     | Use cases, tests, specs, and review notes |
| `next_step`       | string    | Next valid step                           |
| `updated_at`      | timestamp | Last updated time                         |

---

## MCP Tools and Resources

> Legend: ✅ Implemented · ⚠️ Partial (code exists, not registered) · 🗓️ Planned

### Auth Tools

These tools are **not grantable** to MCP client principals via `tool_scopes`.
`minder_auth_whoami` is always available to all authenticated principals.

| Tool                              | Status | Description                                                     |
| --------------------------------- | ------ | --------------------------------------------------------------- |
| `minder_auth_login`               | ✅     | Exchange a human admin API key for a JWT bearer token           |
| `minder_auth_exchange_client_key` | ✅     | Exchange a client API key for a scoped short-lived access token |
| `minder_auth_whoami`              | ✅     | Return the current principal identity, role, and active scopes  |
| `minder_auth_manage`              | ✅     | Admin-only: list users and run auth management actions          |
| `minder_auth_create_client`       | ✅     | Admin-only: create a new MCP client and issue its API key       |
| `minder_auth_ping`                | ✅     | Verify auth is working and the current principal can call tools |

### Session Tools

All session tools are **always available** to any authenticated principal
(human or client) — no explicit `tool_scopes` grant is required.

| Tool                     | Status | Description                                                             |
| ------------------------ | ------ | ----------------------------------------------------------------------- |
| `minder_session_create`  | ✅     | Create a named, persisted session; pass `name` for cross-env recovery   |
| `minder_session_find`    | ✅     | Find a session by name — primary cross-environment recovery entry point |
| `minder_session_list`    | ✅     | List all sessions owned by the calling principal, newest-first          |
| `minder_session_save`    | ✅     | Persist task state and active skills; call after each wave of work      |
| `minder_session_restore` | ✅     | Load saved state and context for an existing session by UUID            |
| `minder_session_context` | ✅     | Update branch and open-file context for an existing session             |

### Workflow Tools

| Tool                     | Status | Description                                                        |
| ------------------------ | ------ | ------------------------------------------------------------------ |
| `minder_workflow_get`    | ✅     | Return the active workflow for a repository                        |
| `minder_workflow_step`   | ✅     | Return the current step, blockers, and next step                   |
| `minder_workflow_update` | ✅     | Mark a step complete or attach an artifact                         |
| `minder_workflow_guard`  | ✅     | Validate whether a requested action is allowed in the current step |

### Core Query and Search Tools

| Tool                   | Status | Description                                      |
| ---------------------- | ------ | ------------------------------------------------ |
| `minder_query`         | ✅     | Run the full agentic RAG pipeline                |
| `minder_search`        | ✅     | Run semantic search without LLM generation       |
| `minder_search_code`   | ✅     | Search code snippets and patterns                |
| `minder_search_errors` | ✅     | Search similar historical errors and resolutions |

### Memory Tools

Memory tools operate on the **Skill Store** (vector-backed) via the memory layer.
The `minder_memory_compact` tool mentioned in earlier drafts is not implemented.

| Tool                   | Status | Description                            |
| ---------------------- | ------ | -------------------------------------- |
| `minder_memory_store`  | ✅     | Store a skill, document, rule, or note |
| `minder_memory_recall` | ✅     | Recall entries by semantic similarity  |
| `minder_memory_list`   | ✅     | List stored entries                    |
| `minder_memory_delete` | ✅     | Delete a memory entry by ID            |

### Skill Tools (Planned — Phase 5 backlog)

Distinct from memory tools: skill tools expose workflow-step-aware retrieval
and quality signal management. The backing store and embedding pipeline are
already in place; the MCP surface layer has not been built yet.

| Tool                  | Status | Description                                                           |
| --------------------- | ------ | --------------------------------------------------------------------- |
| `minder_skill_store`  | 🗓️     | Store a reusable skill with workflow-step, provenance, and tag labels |
| `minder_skill_recall` | 🗓️     | Retrieve skills compatible with the current workflow step             |
| `minder_skill_list`   | 🗓️     | List skills by project, step, tags, or quality score                  |
| `minder_skill_update` | 🗓️     | Update skill content, metadata, and quality signals                   |
| `minder_skill_delete` | 🗓️     | Remove obsolete or invalid skills                                     |

Planned admin-surface expansion:

- Dashboard skill CRUD uses the same underlying skill catalog
- remote imports from GitHub, GitLab, and generic Git sources become auditable admin operations
- manual curation can override imported content without losing provenance

### Ingestion Tools (Partial — not yet registered in transport)

The tool class `IngestTools` is implemented in `src/minder/tools/ingest.py` but
is not yet wired into the MCP transport. Registration is a Phase 5 task.

| Tool                      | Status | Description                                 |
| ------------------------- | ------ | ------------------------------------------- |
| `minder_ingest_file`      | ⚠️     | Ingest a local file into the document store |
| `minder_ingest_directory` | ⚠️     | Batch-ingest a directory                    |
| `minder_ingest_url`       | ⚠️     | Fetch and ingest a URL                      |
| `minder_ingest_git`       | ⚠️     | Shallow-clone and ingest a Git repository   |

### Admin Tools (Planned — Phase 5 backlog)

| Tool             | Status | Description                              |
| ---------------- | ------ | ---------------------------------------- |
| `minder_status`  | 🗓️     | Health check, stats, and active sessions |
| `minder_config`  | 🗓️     | Get or update runtime configuration      |
| `minder_reindex` | 🗓️     | Reindex vector collections               |

---

## MCP Resources

| Resource                 | Status | Description                          |
| ------------------------ | ------ | ------------------------------------ |
| `minder://skills`        | ✅     | List all skills with title and tags  |
| `minder://repos`         | ✅     | List repos with workflow state       |
| `minder://stats`         | ✅     | Query count, avg latency, error rate |
| `minder://sessions/{id}` | 🗓️     | Session state by ID (planned)        |

## MCP Prompts

| Prompt     | Status | Description                                          |
| ---------- | ------ | ---------------------------------------------------- |
| `debug`    | ✅     | Debugging prompt template with error-store context   |
| `review`   | ✅     | Code review prompt template with skill-store context |
| `explain`  | ✅     | Explanation prompt template with document context    |
| `tdd_step` | ✅     | Prompt template for the current TDD workflow step    |

---

## Workflow-Orchestrated Retrieval Contract

When workflow enforcement is enabled for a repository:

- Every retrieval call must receive workflow context (`workflow_id`, `current_step`, `required_artifacts`)
- Memory and skill ranking must include step-compatibility scoring
- Session restore must include the latest validated instruction envelope
- Gemma 3/4 local synthesis output must be scoped to the current step and blocked actions

---

## Configuration Example

```toml
[server]
name = "minder"
version = "0.1.0"
transport = "sse"
host = "0.0.0.0"
port = 8800
log_level = "info"

[auth]
enabled = true
jwt_secret = "${MINDER_JWT_SECRET}"
jwt_expiry_hours = 24
api_key_prefix = "mk_"
default_admin_email = "${MINDER_ADMIN_EMAIL}"

[embedding]
provider = "fastembed"
runtime = "auto"
fastembed_model = "mixedbread-ai/mxbai-embed-large-v1"
dimensions = 1024
openai_api_key = "${OPENAI_API_KEY}"
openai_model = "text-embedding-3-small"

[llm]
provider = "litert"
litert_model_path = "~/.minder/models/gemma-4-E2B-it.litertlm"
context_length = 131072
temperature = 0.1
openai_api_key = "${OPENAI_API_KEY}"
openai_model = "gpt-4o-mini"

[vector_store]
provider = "milvus_standalone"
host = "localhost"
port = 19530

[relational_store]
provider = "mongodb"
uri = "${MONGODB_URI}"
db_name = "minder"

[retrieval]
top_k = 10
rerank_top_n = 5
similarity_threshold = 0.7
hybrid_alpha = 0.7

[cache]
enabled = true
provider = "redis"
redis_url = "${REDIS_URL}"
ttl_seconds = 3600

[verification]
enabled = true
sandbox = "docker"
timeout_seconds = 30
docker_image = "minder-sandbox:latest"

[workflow]
enforcement = "strict"
default_workflow = "tdd"
repo_state_dir = ".minder"
block_step_skips = true

[seeding]
skills_repo = ""
skills_branch = "main"
skills_path = "skills/"
```

Current live configuration remains GitHub-oriented via generic Git clone settings. A future provider-aware admin import surface should extend this with provider and credential references rather than overloading the base seed path.
