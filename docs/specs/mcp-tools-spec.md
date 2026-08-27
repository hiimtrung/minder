# MCP Tools Specification (Lean & Fast Endpoints)

All MCP Tools adhere to the **Lean & Deterministic** standard: zero nested LLM reasoning loops, response latency `< 50ms`.

---

## 1. Tool Endpoints

### `minder_search_code`
- **Description**: Fast semantic and structural search in the Workspace repository codebase. Returns code chunks with full content, symbol names, and line numbers.
- **Input Arguments**:
  - `query: str` (Required): Keywords or description of code logic.
  - `workspace_id: str` (Optional): Target Workspace UUID.
  - `repo_name: str` (Optional): Target repository filter.
  - `limit: int` (Default: 5, Max: 20): Maximum results to return.
- **Output Response**:
  ```json
  [
    {
      "path": "src/auth/jwt.py",
      "symbol_name": "verify_token",
      "language": "python",
      "start_line": 45,
      "end_line": 78,
      "content": "def verify_token(token: str) -> Claims:\n    ...\n    return claims",
      "score": 0.892
    }
  ]
  ```

### `minder_search_contracts`
- **Description**: Query interface contracts (API Routes, DTO Schemas, gRPC methods, event schemas) across repos in a Workspace to prevent AI hallucination.
- **Input Arguments**:
  - `query: str` (Required): Route path or DTO struct name.
  - `workspace_id: str` (Optional): Workspace UUID.
  - `kind: str` (Optional): `"http_route" | "dto_schema" | "grpc_method" | "event_schema"`.
  - `limit: int` (Default: 5).
- **Output Response**:
  ```json
  [
    {
      "identifier": "POST /api/v1/auth/login",
      "kind": "http_route",
      "repo_name": "auth-service",
      "source_file": "src/routes/auth.ts",
      "start_line": 20,
      "end_line": 45,
      "definition": "router.post('/login', validate(LoginSchema), handler);",
      "metadata": {"auth_required": false}
    }
  ]
  ```

### `minder_memory_recall`
- **Description**: Retrieve project memories and architectural decisions.
- **Input Arguments**:
  - `query: str` (Required).
  - `limit: int` (Default: 5).
- **Output Response**:
  ```json
  [
    {
      "id": "uuid-string",
      "title": "Auth Architecture 2026",
      "content": "All services must use PKCE JWT via header X-Auth-Token",
      "tags": ["auth", "architecture"],
      "score": 0.95
    }
  ]
  ```

### `minder_session_boot` / `minder_session_save`
- **Description**: Restore and checkpoint session states seamlessly across developer devices (Laptop, Workstation, Remote VM).
- **Latency**: `< 10ms`.
