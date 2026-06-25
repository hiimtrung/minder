# 06. Operations and Delivery

## Final Directory Structure

```text
minder/
├── LICENSE
├── README.md
├── pyproject.toml
├── uv.lock
├── minder.toml
├── .env.example
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── release.yml
├── src/minder/
│   ├── __init__.py
│   ├── server.py
│   ├── config.py
│   ├── auth/
│   │   ├── models.py
│   │   ├── service.py
│   │   ├── middleware.py
│   │   ├── keys.py
│   │   └── rate_limiter.py
│   ├── transport/
│   │   ├── stdio.py
│   │   └── sse.py
│   ├── tools/
│   │   ├── auth.py
│   │   ├── workflow.py
│   │   ├── search.py
│   │   ├── query.py
│   │   ├── memory.py
│   │   ├── session.py
│   │   ├── ingest.py
│   │   └── admin.py
│   ├── resources/
│   │   ├── skills.py
│   │   ├── repos.py
│   │   └── stats.py
│   ├── prompts/
│   │   ├── debug.py
│   │   ├── review.py
│   │   ├── explain.py
│   │   └── tdd_step.py
│   ├── graph/
│   │   ├── state.py
│   │   ├── graph.py
│   │   ├── edges.py
│   │   └── nodes/
│   │       ├── workflow_planner.py
│   │       ├── planning.py
│   │       ├── retriever.py
│   │       ├── reranker.py
│   │       ├── reasoning.py
│   │       ├── llm.py
│   │       ├── guard.py
│   │       ├── verification.py
│   │       ├── evaluator.py
│   │       └── reflection.py
│   ├── embedding/
│   │   ├── base.py
│   │   ├── local.py
│   │   └── openai.py
│   ├── llm/
│   │   ├── base.py
│   │   ├── local.py
│   │   └── openai.py
│   ├── store/
│   │   ├── base.py
│   │   ├── vector.py
│   │   ├── relational.py
│   │   ├── repo_state.py
│   │   ├── history.py
│   │   ├── error.py
│   │   ├── document.py
│   │   ├── rule.py
│   │   ├── feedback.py
│   │   ├── workflow.py
│   │   └── graph.py
│   ├── retrieval/
│   │   ├── hybrid.py
│   │   ├── mmr.py
│   │   └── multi_hop.py
│   ├── chunking/
│   │   ├── splitter.py
│   │   └── code_splitter.py
│   ├── cache/
│   │   ├── lru.py
│   │   └── redis.py
│   ├── learning/
│   │   ├── pattern_extractor.py
│   │   ├── skill_synthesizer.py
│   │   ├── error_learner.py
│   │   └── quality_optimizer.py
│   ├── observability/
│   │   ├── tracing.py
│   │   ├── metrics.py
│   │   └── logging.py
│   ├── models/
│   │   ├── user.py
│   │   ├── skill.py
│   │   ├── memory.py
│   │   ├── session.py
│   │   ├── workflow.py
│   │   ├── repository.py
│   │   ├── document.py
│   │   ├── error.py
│   │   ├── rule.py
│   │   └── feedback.py
│   └── migration/
│       └── alembic/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_auth.py
│   │   ├── test_workflow.py
│   │   ├── test_repo_state.py
│   │   ├── test_embedding.py
│   │   ├── test_store.py
│   │   ├── test_nodes.py
│   │   └── test_retrieval.py
│   ├── integration/
│   │   ├── test_pipeline.py
│   │   ├── test_mcp_tools.py
│   │   ├── test_auth_flow.py
│   │   ├── test_workflow_flow.py
│   │   └── test_ingest.py
│   └── e2e/
│       └── test_full_query.py
├── docker/
│   ├── Dockerfile
│   ├── Dockerfile.sandbox
│   ├── docker-compose.local.yml
│   ├── docker-compose.yml
│   └── docker-compose.yml
├── dashboard/
│   ├── backend/
│   └── frontend/
├── docs/
│   ├── PLAN.md
│   └── plan/
│       ├── 01-product-scope.md
│       ├── 02-architecture.md
│       ├── 03-data-model-and-tools.md
│       ├── 04-workflow-governance.md
│       ├── 05-implementation-phases.md
│       └── 06-operations-and-delivery.md
└── scripts/
    ├── seed_skills.py
    └── create_admin.py
```

## Risks and Mitigations

| Risk                                                                     | Impact | Mitigation                                                                   |
| ------------------------------------------------------------------------ | ------ | ---------------------------------------------------------------------------- |
| `nomic-ai/nomic-embed-text-v1.5-GGUF` is too heavy for some local machines | High   | Optimize quantization, document hardware requirements, allow OpenAI fallback |
| `unsloth/Qwen3.5-2B-GGUF` quality is insufficient for complex tasks | Medium | Route allowed complex queries to OpenAI                                      |
| Turbovec performance is not enough for very large team scale             | Medium | Evaluate distributed vector store options (e.g. Qdrant Standalone) for Phase 4 |
| Workflow enforcement becomes too rigid                                   | Medium | Support strict and advisory modes                                            |
| Repository-local state drifts from centralized state                     | High   | Add sync and conflict detection between repo and server                      |
| Docker sandbox escapes or misconfiguration                               | High   | Use locked-down containers, no network, read-only root, and resource limits  |
| Multi-user data isolation bugs                                           | High   | Enforce repo and user scoping on every query and tool                        |
| API key leakage                                                          | High   | Store only bcrypt hashes, support rotation, and maintain audit logs          |
| Concurrent user load affects latency                                     | Medium | Async I/O, pooling, caching, and rate limits                                 |
| GitHub source for seeded skills is unavailable                           | Low    | Cache imported skills locally                                                |
| Dashboard adds scope creep too early                                     | Medium | Keep dashboard minimal until Phase 4                                         |

## CI/CD Pipeline

### CI Workflow (`ci.yml`)

Runs on every pull request and push to main.

```yaml
1. Checkout
2. Setup Python 3.14 and uv
3. Install dependencies
4. Ruff lint and format check
5. Type check
6. Unit tests
7. Integration tests
8. Coverage report
9. Docker build verification
```

### Release Workflow (`release.yml`)

Runs on version tags.

```yaml
1. Checkout
2. Run full CI
3. Build multi-arch Docker images
4. Push images to ghcr.io
5. Build Python package
6. Create GitHub Release
7. Publish package artifacts
8. Publish sandbox image
```

### Published Artifacts

| Artifact                                 | Description                |
| ---------------------------------------- | -------------------------- |
| `ghcr.io/<org>/minder:<version>`         | Main MCP server image      |
| `ghcr.io/<org>/minder:latest`            | Latest stable server image |
| `ghcr.io/<org>/minder-sandbox:<version>` | Sandbox image              |
| Python wheel and sdist                   | Python package artifacts   |

## Success Metrics

| Metric                    | Phase 1 Target   | Phase 4 Target               |
| ------------------------- | ---------------- | ---------------------------- |
| Search latency p95        | Less than 500 ms | Less than 200 ms             |
| Full query latency p95    | Not yet targeted | Less than 5 s with local LLM |
| Search relevance MRR@10   | Greater than 0.6 | Greater than 0.8             |
| Store and recall accuracy | 100%             | 100%                         |
| Memory usage              | Less than 2 GB   | Less than 4 GB               |
| Test coverage             | Greater than 80% | Greater than 85%             |
| MCP tool success rate     | Greater than 95% | Greater than 99%             |
| Auth success rate         | Greater than 99% | Greater than 99.9%           |
| Concurrent users          | 5                | 50+                          |
| Workflow compliance rate  | Greater than 90% | Greater than 98%             |
| CI pipeline time          | Less than 5 min  | Less than 10 min             |
