# ADR 0003: AST-Aware Code Chunking & Lean MCP Tool Performance

## Status
Accepted

## Context
1. MCP tools (`minder_memory_recall`, `minder_skill_recall`, `minder_session_boot`) previously invoked LangGraph sub-graphs with 2–6 nested LLM calls, causing latencies of 15–45 seconds.
2. `minder_search_code` only returned metadata without code snippets, while file ingestion embedded entire files as single vectors, truncating 90% of large files.

## Decision
1. Transform all MCP retrieval tools into **Lean & Deterministic Endpoints (< 50ms)**, removing internal LLM reasoning chains.
2. Deploy an AST-aware `CodeSplitter` to partition code along function/class/interface boundaries across multiple languages (Python, TS/JS, Java, Go, Rust, C++, Configs).
3. `minder_search_code` returns full snippet content (20–50 lines), start line, and end line.

## Consequences
- Retrieval response latencies dropped below 50ms (300x speedup).
- AI Agents immediately read and understand code context without issuing secondary file-read tool calls.
