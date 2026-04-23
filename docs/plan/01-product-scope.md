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

## Confirmed Decisions

| #   | Topic                | Decision                                                                                    |
| --- | -------------------- | ------------------------------------------------------------------------------------------- |
| 1   | Target users         | Team, shared server, multi-user                                                             |
| 2   | Offline-first        | Mandatory local-first operation with optional cloud fallback                                |
| 3   | Model priority       | `gemma-4-E4B-it.litertlm` (LiteRT-LM) and `mxbai-embed-large-v1` (FastEmbed) are mandatory |
| 4   | MCP transport        | SSE from Phase 1, stdio for local dev                                                       |
| 5   | Knowledge graph      | Included in Phase 3                                                                         |
| 6   | Verification sandbox | Docker is mandatory in production                                                           |
| 7   | Existing data        | Skills may be seeded or imported from external Git repositories including GitHub and GitLab |
| 8   | Performance target   | Reasonable responsiveness, not ultra-low-latency at the expense of quality                  |
| 9   | Concurrent users     | Multi-user with identity from email and Git username                                        |
| 10  | CI/CD                | Required from Phase 1 with GitHub Actions, Releases, and Packages                           |
| 11  | Workflow governance  | Required; Minder must enforce configured engineering workflows                              |
| 12  | Repository state     | Required; workflow state and context must be persisted in each repository                   |
| 13  | Dashboard            | Required for workflow configuration, governance, and direct skill catalog management        |

## Product Direction Update — 2026-04-15

- Skill lifecycle is now a product capability: operators must be able to import and manage skills directly from the Dashboard.
- External skill sources must be treated as Git-provider-agnostic, not GitHub-only.
- Repository graph intelligence is metadata-first: file/function/controller/message-flow metadata is the durable asset, while full-source storage is explicitly discouraged.
