# 05. Implementation Phases

## Technology Stack

| Component          | Technology                                          | Reason                                             |
| ------------------ | --------------------------------------------------- | -------------------------------------------------- |
| Language           | Python 3.14+                                        | Native fit for LangGraph and ML tooling            |
| MCP SDK            | Official Python `mcp` SDK                           | MCP protocol support                               |
| Orchestrator       | LangGraph                                           | Graph-based agentic workflow engine                |
| Vector DB          | Milvus Lite to Milvus Standalone                    | Lightweight start with scale path                  |
| Relational DB      | SQLite to PostgreSQL                                | Metadata, users, sessions, and audit               |
| Embedding          | `ggml-org/embeddinggemma-300M-GGUF` GGUF, mandatory | Offline-first, optimized for `llama.cpp`           |
| Embedding runtime  | `llama.cpp` via `llama-cpp-python`                  | Shared local inference runtime                     |
| Embedding fallback | OpenAI `text-embedding-3-small`                     | Optional cloud fallback                            |
| LLM                | `ggml-org/gemma-4-E2B-it-GGUF` GGUF, mandatory      | Offline-first, CPU-friendly                        |
| LLM runtime        | `llama.cpp` via `llama-cpp-python`                  | Native GGUF runtime                                |
| LLM fallback       | OpenAI via LiteLLM                                  | Optional cloud routing                             |
| Auth               | PyJWT, bcrypt, API keys                             | Team auth and role control                         |
| Chunking           | LangChain text splitters plus custom code chunking  | Proven chunking patterns                           |
| Reranking          | sentence-transformers cross-encoder                 | Better precision                                   |
| Verification       | Docker sandbox plus pytest                          | Safe execution and testing                         |
| Config             | Pydantic Settings                                   | Strongly typed configuration                       |
| Package manager    | uv                                                  | Fast and reliable Python dependency management     |
| CI/CD              | GitHub Actions                                      | Standardized automation                            |
| Registry           | GitHub Packages and ghcr.io                         | Package and image publishing                       |
| Containerization   | Docker and Docker Compose                           | Dev and prod deployment                            |
| Dashboard backend  | FastAPI or Starlette                                | API for workflow and admin UI                      |
| Dashboard frontend | Astro with Tailwind CSS                             | Workflow and admin UI with static-first deployment |

## Phase 1: Foundation - MCP Server, Auth, Search, CI/CD

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
5. Integrate mandatory `ggml-org/embeddinggemma-300M-GGUF` embeddings through `llama-cpp-python`.
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

## Phase 2: Agentic Pipeline - LangGraph and Guided Execution

**Goal**: Deliver the end-to-end agentic pipeline with workflow-aware reasoning and Docker-based verification.

### Tasks

1. Define LangGraph state.
2. Build Workflow Planner, Planning, Retriever, Reasoning, LLM, Guard, Verification, and Evaluator nodes.
3. Integrate mandatory `ggml-org/gemma-4-E2B-it-GGUF` GGUF through `llama-cpp-python`.
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

## Phase 3: Advanced Retrieval, Knowledge Graph, and Process Intelligence

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

## Phase 4: Production Scale, Multi-User Reliability, and Dashboard

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

## Phase 5: Learning and Self-Improvement

**Goal**: Let Minder learn from successful workflows, failures, and feedback.

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
