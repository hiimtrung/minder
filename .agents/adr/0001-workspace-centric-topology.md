# ADR 0001: Workspace-Centric Topology & Cross-Repo Contract Registry

## Status
Accepted

## Context
In production engineering environments, a system is distributed across multiple Git Repositories (Backend, Frontend, Auth, Shared Schemas). When an AI Agent is restricted to a single local repository, it lacks visibility into peer services and begins hallucinating interface schemas, resulting in integration bugs.

## Decision
1. Introduce the root entity `Workspace` grouping multiple `Repository` entities.
2. Build a `Contract Registry` automatically extracting HTTP Routes, DTO Schemas, gRPC/Protobuf definitions, and Event Schemas from all repos in the Workspace.
3. Provide the MCP tool `minder_search_contracts(workspace_id=...)` enabling AI Agents to query exact peer service contracts.

## Consequences
- Eliminates the cross-service context gap (Zero Hallucinations).
- AI Agents generate frontend and microservice code matching production schemas with 100% fidelity.
