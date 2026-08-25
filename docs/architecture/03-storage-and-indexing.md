# 03. Storage & Indexing — Storage Design And Code Chunking

---

## 1. Relational Storage (SQLite WAL Mode)

Minder uses SQLite with **Write-Ahead Logging (WAL)**:
- `minder.db`: Stores Workspaces, Repositories, Contracts, Memories, Skills, and Sessions.
- `graph.db`: Stores dependency graphs across symbols, files, and API routes.
- **Concurrency Optimization**:
  - `PRAGMA journal_mode = WAL;` (Enables concurrent readers without lock contention).
  - `PRAGMA synchronous = NORMAL;` (Optimal balance of I/O performance and data safety).
  - `PRAGMA busy_timeout = 5000;` (Automatic retry on lock contention up to 5s).

---

## 2. AST-Aware Code Chunking

Minder avoids embedding entire files as monolithic vectors. The `CodeSplitter` parses and splits code along syntactic boundaries:

- **Python**: Slices along `def`, `async def`, and `class` boundaries, prepending module-level imports.
- **TypeScript / JavaScript**: Slices along `function`, `class`, `interface`, and `export const`.
- **Java / C++ / Go / Rust**: Slices along top-level symbol signatures and brace-depth blocks.
- **HTML / CSS / SCSS / Configs**: Slices along logical sections.

Each chunk is stored with rich metadata:
`{workspace_id, repo_id, file_path, symbol_name, language, start_line, end_line, content}`.

---

## 3. Vector Indexing (Turbovec ANN Index)

Turbovec provides 4-bit vector quantization (`vectors.tvim`):
- Cosine similarity search across millions of chunks in `< 5ms`.
- Compact memory footprint and fast startup loading.
