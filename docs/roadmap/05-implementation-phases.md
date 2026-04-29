# 05. Implementation Phases

Canonical technology stack reference: [System Design](../architecture/system-design.md)

---

## Phase 1: Foundation (DONE)

**Goal**: Deliver a working SSE-first MCP server with authentication, repository-local state, basic search, and baseline CI/CD.

### Deliverables

```text
pyproject.toml
src/minder/server.py
src/minder/config.py
src/minder/auth/*
src/minder/transport/{stdio,sse}.py
src/minder/tools/{auth,search,memory,workflow}.py
src/minder/store/{base,vector,relational,repo_state}.py
src/minder/models/{user,skill,memory,session,workflow,repo}.py
.github/workflows/{ci,release}.yml
docker/Dockerfile.api
docker/Dockerfile.dashboard
docker/docker-compose.local.yml
scripts/{download_models,seed_skills,create_admin}.py|sh
```

### Tasks

1. Initialize the Python project with `uv`, linting, formatting, and type checking.
2. Implement the auth layer with user model, API keys, JWTs, and RBAC.
3. Implement SSE transport as the primary transport and stdio for local dev.
4. Add auth middleware for SSE connections.
5. Integrate mandatory `mixedbread-ai/mxbai-embed-large-v1` embeddings through `FastEmbed`.
6. Add optional OpenAI embedding fallback.
7. Implement Milvus Lite for semantic search.
8. Implement SQLite metadata storage for users, sessions, workflows, and repo state.
9. Add repository-local `.minder/` state management.
10. Implement workflow tools for current-step and next-step guidance.
11. Implement basic semantic search and memory tools.
12. Add skill seeding from external Git source.
13. Add Docker-based local development stack.
14. Add GitHub Actions CI and release automation.
15. Add baseline tests for auth, search, workflow state, and repo state.

### Validation

- Team members connect through SSE.
- Users authenticate successfully.
- Repository-local state is written and restored.
- Workflow tools report the current step and next step.
- CI pipeline passes.

## Phase 2: Agentic Pipeline (DONE)

**Goal**: Deliver the end-to-end agentic pipeline with workflow-aware reasoning and Docker-based verification.

### Tasks

1. Define LangGraph state.
2. Build Workflow Planner, Planning, Retriever, Reasoning, LLM, Guard, Verification, and Evaluator nodes.
3. Integrate mandatory `gemma-4-E2B-it.litertlm` through `LiteRT-LM`.
4. Add optional OpenAI fallback through LiteLLM.
5. Implement Docker sandbox verification.
6. Keep subprocess verification available in dev mode only.
7. Add user-scoped history and error stores.
8. Implement `minder_query`, `minder_search_code`, and `minder_search_errors`.
9. Make the workflow engine inject current-step instructions into the prompt.
10. Make the MCP explicitly tell the primary LLM the next valid workflow step.

### Validation

- A TDD-configured repository causes the LLM to write tests before implementation.
- Generated code is verified in Docker sandbox.
- Repository workflow state advances correctly.

## Phase 3: Advanced Retrieval & Graph (DONE)

**Goal**: Improve retrieval quality and add relationship-aware repository intelligence.

Direction note: the delivered Phase 3 baseline remains valid, but future performance work should prefer repo-local metadata extraction through `minder-cli` and delta sync instead of broad server-side graph refresh.

### Tasks

1. Add reranking, BM25 hybrid retrieval, and multi-hop retrieval.
2. Implement the knowledge graph store.
3. Implement document, rule, and feedback stores.
4. Add AST-aware code chunking.
5. Track repository relationships such as modules, services, ownership, and dependencies.
6. Keep graph construction metadata-first so repository intelligence stores structure, not full source dumps.
7. Add richer workflow intelligence based on repo relationships and artifact lineage.
8. Add ingestion tools for repository scanning and artifact extraction.
9. Add MCP resources and prompts for workflow-aware operation.

### Validation

- Multi-hop queries across code, docs, and repository relationships return better results.
- The LLM can retrieve use cases, test artifacts, and previous workflow state from the repository itself.

## Phase 4: Production Scale & Dashboard (DONE)

**Goal**: Make the system production-ready for teams and add a dashboard for workflow administration.

### Tasks

1. Move from SQLite to PostgreSQL for production.
2. Move from Milvus Lite to Milvus Standalone.
3. Add Redis caching.
4. Add per-user rate limiting and quotas.
5. Add tracing, metrics, structured logs, and audit trails.
6. Add production Docker Compose stack.
7. Build the dashboard for workflow config, repo policies, user management, observability, and skill catalog management.
8. Add CI/CD status integration in the dashboard.
9. Add load testing and multi-user performance testing.
10. Run a security review for auth, isolation, and sandboxing.

### Validation

- Admins can configure workflows in the dashboard.
- Repository state and progress are visible in the dashboard.
- Concurrent users can use the system reliably.

## Phase 5: Learning & Skill Catalog (IN PROGRESS)

**Goal**: Let Minder learn from successful workflows, failures, and feedback, while expanding the dashboard into a local-LLM control surface that can use the full MCP toolset.

Direction note: Phase 5 graph work continues to follow the metadata-first policy and now has a dedicated transition roadmap for CLI edge extraction and fast graph sync.

### Tasks

1. Extract reusable patterns from workflow histories.
2. Synthesize new skills from successful sessions.
3. Learn from error resolutions.
4. Optimize retrieval parameters from feedback.
5. Add reflection capabilities for post-run evaluation.
6. Add Dashboard-backed skill CRUD and remote import from GitHub, GitLab, and generic Git repositories.
7. Keep GraphNode storage limited to metadata and long-lived reusable excerpts.
8. Add experimentation support for workflow and retrieval strategy variants.
9. Add a dashboard-native local-LLM chat shell that can use the same MCP tools available to IDE agents for question-answering, operational workflows, and CRUD over managed data.

## Phase 6: Branch Topology & IDE Bootstrap (DONE)

**Goal**: automate repository branch-topology discovery and repository-local IDE bootstrap in the CLI pipeline after the learning/skill backlog is in place, while adding secure installer/update flows for Minder server and Minder CLI without diluting the runtime search and impact follow-up work.

### Tasks

1. Extend `minder-cli` and the repo scanner to infer `branch_relationships` from local branch state, configured remotes, and worktree context.
2. Normalize detected branch links against the persisted repository landscape so sync payloads can submit stable `repo/branch -> repo/branch` relationships.
3. Add review-safe fallback behavior when inferred topology is ambiguous, incomplete, or conflicts with admin-managed links.
4. Add `minder-cli` commands that install MCP servers, instructions, and agents for supported IDEs into the current repository instead of global user config.
5. Make repo-local IDE bootstrap version-aware so existing config is appended or patched in place during updates instead of replaced blindly.
6. Add secret-safe handling for repository-local MCP config so client keys are not committed, including `.gitignore` automation and/or a secure indirection mechanism.
7. Ship quick-install scripts for Minder server and Minder CLI that validate environment compatibility on macOS, Linux, and Windows before installing required components.
8. Publish the installer scripts and usage guidance as GitHub Release assets and release documentation.
9. Validate that automatic branch-topology submission and repo-local IDE bootstrap do not regress the manual dashboard branch-link workflow or expose secrets accidentally.

### Validation

- CLI sync can submit inferred `branch_relationships` without requiring dashboard-only manual entry for the common case.
- Ambiguous or conflicting branch topology is surfaced safely instead of silently creating incorrect cross-repo links.
- Repository-local IDE bootstrap can install or update Minder MCP/instructions/agents for supported IDEs without overwriting unrelated config.
- Client keys are not exposed through committed repository config in the default installation path.
- Cross-platform server and CLI install scripts validate prerequisites and complete successfully on supported environments.
- Existing repository landscape, search, and impact workflows continue to function when automatic topology detection and repo-local IDE bootstrap are enabled.
