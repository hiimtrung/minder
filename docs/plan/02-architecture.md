# 02. Architecture

Canonical reference:
- [System Design](/Users/trungtran/ai-agents/minder/docs/system-design.md)

This planning document keeps the architecture-specific implementation notes that support the phased plan.
It is not the primary source of truth for runtime topology anymore.

## Expanded Architecture

Runtime topology, dashboard serving, storage topology, and clean architecture boundaries are documented in:
- [System Design](/Users/trungtran/ai-agents/minder/docs/system-design.md)

This file keeps the planning-level node and orchestration notes that matter for implementation sequencing.

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
  3. Optionally merge keyword search and BM25
  4. De-duplicate and filter by score threshold
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
