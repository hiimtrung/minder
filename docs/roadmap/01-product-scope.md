# 01. Product Scope

## Project Overview

Minder is a Model Context Protocol server that provides Agentic RAG with a multi-tier knowledge architecture. When connected to any MCP-compatible AI client such as GitHub Copilot, Claude Desktop, Cursor, or a custom agent, Minder provides capabilities for:

- Semantic search across multiple knowledge layers
- Multi-tier memory and knowledge management
- Agentic planning and structured reasoning
- Verification through tests and sandbox execution
- Workflow governance for software delivery processes

## Deployment Model

| Aspect         | Decision                                                                     |
| -------------- | ---------------------------------------------------------------------------- |
| Target users   | Team, shared server, multi-user                                              |
| User identity  | Email plus Git username, with isolated user and repository context           |
| Authentication | API key plus JWT with role-based access control                              |
| Network model  | Offline-first with mandatory local models; OpenAI fallback when available    |
| Transport      | SSE from Phase 1, stdio for local development                                |
| Verification   | Docker sandbox is mandatory in production; subprocess is allowed in dev mode |
| Skill seeding  | Initial skill import from external Git repositories such as GitHub or GitLab |
| CI/CD          | GitHub Actions, GitHub Releases, and GitHub Packages from Phase 1            |

## Why build this as an MCP server?

| Benefit    | Explanation                                                                         |
| ---------- | ----------------------------------------------------------------------------------- |
| Universal  | Any MCP-capable AI client can use it                                                |
| Composable | It can work alongside GitHub, filesystem, database, and other MCP servers           |
| Stateful   | MCP sessions make it possible to preserve context across tool calls                 |
| Extensible | New tools, resources, and prompts can be added without changing the client          |
| Governed   | The MCP can actively steer the primary LLM through an approved engineering workflow |

## Core Product Requirement: Workflow Governance

Minder is not only a retrieval and memory system. It must also be able to govern software delivery workflows for a company.

Example target workflow:

1. Intake the problem.
2. Analyze the problem.
3. Derive use cases and acceptance criteria.
4. Write tests first.
5. Implement until tests pass.
6. Review, verify, and release.

If a company chooses to enforce TDD, Minder must be configurable so that the primary LLM is guided to follow that exact sequence. After a workflow is configured, potentially through a dashboard, Minder should:

- Tell the LLM which step it is currently in
- Provide the required context for that step
- Prevent skipping required gates when configured as mandatory
- Save workflow state per repository
- Save repository-specific context, artifacts, decisions, and relationships inside that repository
- Tell the LLM what the next valid step is
- Surface missing prerequisites such as absent tests, missing use cases, or incomplete analysis

This makes Minder both a knowledge system and a process orchestration layer for engineering teams.

---

For current technical decisions and architecture, see [System Design](../architecture/system-design.md).

## Product Direction Update — 2026-04-15

- Skill lifecycle is now a product capability: operators must be able to import and manage skills directly from the Dashboard.
- External skill sources must be treated as Git-provider-agnostic, not GitHub-only.
- Repository graph intelligence is metadata-first: file/function/controller/message-flow metadata is the durable asset, while full-source storage is explicitly discouraged.
