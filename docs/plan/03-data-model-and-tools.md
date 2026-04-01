# 03. Data Model and MCP Surface

## Data and Memory Stores

### Skill Store

| Field           | Type         | Description                                   |
| --------------- | ------------ | --------------------------------------------- |
| `id`            | UUID         | Primary key                                   |
| `title`         | string       | Skill title                                   |
| `content`       | text         | Code snippet, API usage, pattern, or guidance |
| `language`      | string       | Programming language                          |
| `tags`          | string[]     | Classification labels                         |
| `embedding`     | vector(1024) | Qwen embedding                                |
| `usage_count`   | int          | Retrieval count                               |
| `quality_score` | float        | Feedback-derived quality score                |
| `created_at`    | timestamp    | Created time                                  |
| `updated_at`    | timestamp    | Last updated time                             |

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

| Field           | Type         | Description                           |
| --------------- | ------------ | ------------------------------------- |
| `id`            | UUID         | Primary key                           |
| `error_code`    | string       | Standardized error code               |
| `error_message` | text         | Original message                      |
| `stack_trace`   | text         | Stack trace                           |
| `context`       | jsonb        | Query, input, state, and tool context |
| `resolution`    | text         | Known resolution if available         |
| `embedding`     | vector(1024) | Similar-error retrieval embedding     |
| `resolved`      | boolean      | Resolution status                     |
| `created_at`    | timestamp    | Created time                          |

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

| Field             | Type      | Description                               |
| ----------------- | --------- | ----------------------------------------- |
| `id`              | UUID      | Session ID                                |
| `user_id`         | UUID      | FK to user                                |
| `repo_id`         | UUID      | FK to repository context                  |
| `project_context` | jsonb     | Repo, branch, open files, and environment |
| `active_skills`   | jsonb     | Active skill set                          |
| `state`           | jsonb     | Arbitrary checkpoint state                |
| `ttl`             | int       | Time to live in seconds                   |
| `created_at`      | timestamp | Created time                              |
| `last_active`     | timestamp | Last activity time                        |

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

| Field         | Type         | Description                         |
| ------------- | ------------ | ----------------------------------- |
| `id`          | UUID         | Primary key                         |
| `title`       | string       | Document title                      |
| `content`     | text         | Raw content                         |
| `doc_type`    | enum         | markdown, code, api_spec, or config |
| `source_path` | string       | Original source path                |
| `chunks`      | jsonb        | Chunked content with offsets        |
| `embedding`   | vector(1024) | Document-level embedding            |
| `project`     | string       | Project or repository name          |
| `created_at`  | timestamp    | Import time                         |
| `updated_at`  | timestamp    | Last sync time                      |

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

## MCP Tools and Resources

### Auth Tools

| Tool                 | Description                                                 |
| -------------------- | ----------------------------------------------------------- |
| `minder_auth_login`  | Authenticate a user with email and API key to receive a JWT |
| `minder_auth_whoami` | Return the current user identity and role                   |
| `minder_auth_manage` | Admin tool for user management and API key rotation         |

### Workflow Tools

| Tool                       | Description                                                        |
| -------------------------- | ------------------------------------------------------------------ |
| `minder_workflow_get`      | Return the active workflow for a repository                        |
| `minder_workflow_step`     | Return the current step, blockers, and next step                   |
| `minder_workflow_update`   | Mark a step complete or attach an artifact                         |
| `minder_workflow_guard`    | Validate whether a requested action is allowed in the current step |
| `minder_repo_context_sync` | Save or restore repository context and relationships               |

### Core Tools

| Tool                   | Description                                      |
| ---------------------- | ------------------------------------------------ |
| `minder_query`         | Run the full agentic RAG pipeline                |
| `minder_search`        | Run semantic search without LLM generation       |
| `minder_search_code`   | Search code snippets and patterns                |
| `minder_search_errors` | Search similar historical errors and resolutions |

### Memory Tools

| Tool                    | Description                                    |
| ----------------------- | ---------------------------------------------- |
| `minder_memory_store`   | Store a skill, document, rule, or note         |
| `minder_memory_recall`  | Recall relevant memory for the current context |
| `minder_memory_list`    | List memories by type, tag, or date            |
| `minder_memory_delete`  | Delete a memory entry                          |
| `minder_memory_compact` | Compact and re-vector stale entries            |

### Session Tools

| Tool                     | Description                   |
| ------------------------ | ----------------------------- |
| `minder_session_create`  | Create a new session          |
| `minder_session_save`    | Save session state            |
| `minder_session_restore` | Restore from checkpoint       |
| `minder_session_context` | Get or update session context |

### Ingestion Tools

| Tool                      | Description                                    |
| ------------------------- | ---------------------------------------------- |
| `minder_ingest_file`      | Ingest a file                                  |
| `minder_ingest_directory` | Batch-ingest a directory                       |
| `minder_ingest_url`       | Ingest a URL                                   |
| `minder_ingest_git`       | Ingest a Git repository                        |
| `minder_seed_skills`      | Seed skills from an external GitHub repository |

### Admin Tools

| Tool             | Description                              |
| ---------------- | ---------------------------------------- |
| `minder_status`  | Health check, stats, and active sessions |
| `minder_config`  | Get or update runtime configuration      |
| `minder_reindex` | Reindex collections                      |

### MCP Resources

| Resource                 | Description                           |
| ------------------------ | ------------------------------------- |
| `minder://skills/{id}`   | Skill content by ID                   |
| `minder://sessions/{id}` | Session state                         |
| `minder://repos/{id}`    | Repository context and workflow state |
| `minder://stats`         | System statistics                     |

### MCP Prompts

| Prompt            | Description                                          |
| ----------------- | ---------------------------------------------------- |
| `minder_debug`    | Debugging prompt template with error-store context   |
| `minder_review`   | Code review prompt template with skill-store context |
| `minder_explain`  | Explanation prompt template with document context    |
| `minder_tdd_step` | Prompt template for the current TDD workflow step    |

## Configuration Example

```toml
[server]
name = "minder"
version = "0.1.0"
transport = "sse"
host = "0.0.0.0"
port = 8080
log_level = "info"

[auth]
enabled = true
jwt_secret = "${MINDER_JWT_SECRET}"
jwt_expiry_hours = 24
api_key_prefix = "mk_"
default_admin_email = "${MINDER_ADMIN_EMAIL}"

[embedding]
provider = "llamacpp"
model_name = "Qwen/Qwen3-Embedding-0.6B"
model_path = "~/.minder/models/qwen3-embedding-0.6b.Q8_0.gguf"
dimensions = 1024
openai_api_key = "${OPENAI_API_KEY}"
openai_model = "text-embedding-3-small"

[llm]
provider = "llamacpp"
model_name = "Qwen3.5-0.8B"
model_path = "~/.minder/models/qwen3.5-0.8b-instruct.Q4_K_M.gguf"
context_length = 4096
temperature = 0.1
openai_api_key = "${OPENAI_API_KEY}"
openai_model = "gpt-4o-mini"

[vector_store]
provider = "milvus_lite"
db_path = "~/.minder/data/milvus.db"

[relational_store]
provider = "sqlite"
db_path = "~/.minder/data/minder.db"

[retrieval]
top_k = 10
rerank_top_n = 5
similarity_threshold = 0.7
hybrid_alpha = 0.7

[cache]
enabled = true
provider = "lru"
max_size = 1000
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
