# CONTEXT.md — Ubiquitous Language & Domain Terminology (Minder)

This document defines the standard domain dictionary to ensure precise, concise, and unified communication across developers and AI Agents.

---

## 1. Core Concepts

- **Workspace**: The top-level root unit representing a complete project/solution. A Workspace contains multiple Git Repositories (e.g., `frontend-web`, `backend-api`, `auth-service`, `shared-schemas`).
- **Repository**: A specific Git repository belonging to a Workspace.
- **Contract / Contract Registry**: The structured registry of interfaces and communication protocols across services/repos within a Workspace, including:
  - HTTP Routes (Path, Method, Auth requirements).
  - Request / Response DTO schemas (Pydantic models, TypeScript interfaces, Go structs, Java classes).
  - Protobuf / gRPC service and message definitions.
  - Event Message schemas (Kafka / RabbitMQ payloads).
- **Lean Tool**: A deterministic, high-speed MCP endpoint executing in `< 50ms`, returning raw structured data or code snippets without internal LLM inference loops.
- **Team Hub (Minder Hub)**: Centralized server shared by a team, hosting Knowledge Graphs, Vector Indices, and Shared Memories of a Workspace.
- **Local Edge Daemon (minder connect)**: Lightweight daemon running on a developer's workstation (laptop, desktop, remote VM) that connects to the Hub and automatically synchronizes Git deltas.
- **Code Chunk**: A source code fragment partitioned along AST boundaries (Function, Class, Method) with start line, end line, and module import context.
- **Session Checkpoint**: Work session state (in-progress tasks, current phase, active files, architectural decisions) persisted to enable seamless continuity across multiple devices.

---

## 2. Technical Standards & Boundaries

- **Qwen3.5 2B**: Standardized local LLM (GGUF Q4_K_M) replacing Gemma 4, ensuring clean KV Cache release without RAM leakage.
- **Detached Inference Engine**: Architectural model decoupling LLM inference execution from the Core FastAPI server (via standard OpenAI API / Ollama / standalone llama-server) to avoid I/O blocking.
- **Anti-Hallucination Policy**: Strict rule prohibiting AI Agents from guessing API schemas or code structures; agents must query the Contract Registry or prompt the user ("Grill Me").
