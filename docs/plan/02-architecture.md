# 02. Architecture

Canonical reference:

- [System Design](../../docs/system-design.md)

This planning document keeps the architecture-specific implementation notes that support the phased plan.
It is not the primary source of truth for runtime topology anymore.

## Expanded Architecture

Runtime topology, dashboard serving, storage topology, and clean architecture boundaries are documented in:

- [System Design](../../docs/system-design.md)

This file keeps the planning-level node and orchestration notes that matter for implementation sequencing.

## Knowledge Graph Ingestion Policy

Repository intelligence must treat `GraphNode` as a structural metadata object, not a source-code dump.

Required policy:

- persist files, functions, controllers, routes, queue topics, producers, consumers, and dependency edges as metadata-rich nodes and edges
- store signatures, paths, route patterns, broker/topic names, ownership, and relationship attributes in node metadata
- do not send full file contents into Gemma 3/4 for graph construction by default
- if source text is retained, keep only a bounded reusable excerpt with explicit long-term value

## LangGraph Nodes

### Workflow Planner Node

- Input: User request, repository state, configured workflow, and session context
- Responsibilities:
  1. Determine the current workflow phase
  2. Validate whether prerequisites are satisfied
  3. Decide the next valid step
  4. Generate step-specific guidance for the primary LLM
- Output: Workflow instruction bundle plus next-step directive

### Planning Node

- Input: User query plus session context
- Responsibilities:
  1. Classify intent such as code generation, debugging, search, explanation, or refactoring
  2. Select the correct knowledge layer
  3. Choose a retrieval strategy such as single-hop, multi-hop, or hybrid
  4. Estimate complexity and reasoning depth
- Output: Execution plan

### Retriever Node

- Input: Query, selected knowledge layer, and retrieval strategy
- Responsibilities:
  1. Generate the query embedding
  2. Search Milvus collections
  3. Search graph metadata and relationship stores when the query is structural
  4. Optionally merge keyword search and BM25
  5. De-duplicate and filter by score threshold
- Output: Ranked retrieval candidates

### Reranker Node

- Input: Retrieved candidates plus original query
- Responsibilities:
  1. Cross-encoder reranking
  2. Diversity filtering with MMR
  3. Recency weighting when relevant
- Output: Reranked top-N results

### Reasoning Node

- Input: Retrieved knowledge, workflow instruction bundle, query, and plan
- Responsibilities:
  1. Build the final prompt with retrieved context
  2. Inject workflow rules and step constraints
  3. Enforce the current process stage
  4. Loop if more information is required
- Output: Draft answer plus structured reasoning metadata

### Repository Scanner / Graph Builder

- Input: Repository path, configured scan policy, and language/framework hints
- Responsibilities:
  1. Extract metadata for files, functions, controllers, routes, and queue flow
  2. Build `GraphNode` and `GraphEdge` records without persisting full source by default
  3. Emit reusable excerpts only when a fragment captures a durable contract or pattern
  4. Feed structural context to retrieval and workflow intelligence layers
- Output: Metadata-only graph updates plus optional reusable excerpts

### LLM Node

- Input: Prompt from the Reasoning Node
- Responsibilities:
  1. Route to the mandatory local model by default
  2. Fall back to OpenAI when allowed and available
  3. Stream output for compatible clients
- Output: Generated code or text

### Guard Node

- Input: Generated output
- Responsibilities:
  1. Content safety checks
  2. Hallucination checks against retrieved sources
  3. Syntax checks for generated code
  4. Secrets and PII scanning
- Output: Pass or fail with reasons

### Verification Node

- Input: Generated code or answer
- Responsibilities:
  1. AST or syntax parsing
  2. Docker sandbox execution in production
  3. Subprocess execution in dev mode when allowed
  4. Test execution and result comparison
- Output: Verification report

### Evaluator Node

- Input: Final output, verification report, and feedback
- Responsibilities:
  1. Score quality and correctness
  2. Update quality metrics
  3. Store history and feedback
  4. Trigger memory and workflow learning loops
- Output: Evaluation result and learning signals
