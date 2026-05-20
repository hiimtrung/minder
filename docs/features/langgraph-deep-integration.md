# LangGraph Deep Integration Plan

**Scope**: Tích hợp LangGraph sâu vào bên trong các tools `memory_recall` và `session_restore`, đồng thời nâng cấp toàn bộ graph execution engine theo 6 giai đoạn.

**Nguyên tắc**: Pipeline chạy _bên trong_ tool — MCP surface không thay đổi. Caller (Claude) vẫn gọi cùng tool name, nhận cùng output schema, nhưng bên trong đã có agentic loop + LLM judge.

**Ưu tiên**: Độ chính xác > latency. Judge node dùng LLM local (`llama_cpp`).

---

## Bối cảnh: Tại sao cần thay đổi

### Memory recall hiện tại — one-shot, không có feedback loop

```
minder_memory_recall(query, limit=5)
  → embed(query)
  → cosine_similarity(all_memories)   # so sánh toàn bộ, không có filter thông minh
  → sort by score → top-5             # score=0.15 vẫn được return
  → synthesize_memory_hits()          # synthesis không feed ngược lại retrieval
  → return                            # Claude nhận "nhiễu" như context thật
```

**Rủi ro**: Query quá rộng/hẹp → top-K không cover đủ → Claude dùng incomplete/wrong context để ra quyết định.

### Session restore hiện tại — memory và session hoàn toàn tách rời

```
# Claude phải gọi tuần tự, thủ công:
minder_session_restore(session_id)  →  {step: "implement", task: "fix auth bug"}
minder_memory_recall("authentication")  →  memories về auth nói chung
# Không có liên kết: memories không biết session đang ở step "implement"
# Contradictions giữa session state và memories không được phát hiện
```

**Rủi ro**: Memories recall không đúng phase → Claude hiểu sai context → hành động sai bước.

---

## Tổng quan kiến trúc sau khi tích hợp

```
Tool Layer (MCP surface — không đổi)
├── minder_memory_recall(query, limit) → AgenticMemoryGraph.run()
└── minder_session_restore(session_id) → SessionContextGraph.run()

Graph Layer (LangGraph — MỚI)
├── AgenticMemoryGraph          ← loop: recall → judge → refine → recall
├── SessionContextGraph         ← pipeline: load → targeted_recall → validate → build
├── MinderGraph (đã có)         ← nâng cấp thêm parallel retrieval + checkpointing
└── AgentSupervisor (Phase 6)   ← multi-agent routing

Foundation Layer
├── GraphState (TypedDict + Reducers)   Phase 1
├── MinderCheckpointSaver               Phase 2
└── ParallelRetrieverNode               Phase 3
```

---

## Phase 0: Agentic Memory Recall Loop (NGAY — không cần Phase 1-2)

**Mục tiêu**: Biến `minder_memory_recall` thành agentic loop với LLM judge, chạy bên trong tool.

**Files cần tạo/sửa**:

- `src/minder/graph/memory_graph.py` — **TẠO MỚI**
- `src/minder/graph/session_graph.py` — **TẠO MỚI**
- `src/minder/tools/memory.py` — sửa `minder_memory_recall` và `minder_session_restore`

### 0A. AgenticMemoryGraph

**State**:

```python
# src/minder/graph/memory_graph.py
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph


class MemoryRecallState(TypedDict):
    # --- Input (không đổi qua các iteration) ---
    original_query: str
    current_step: str | None          # workflow step context
    artifact_type: str | None
    target_count: int                 # số memories cần tìm
    min_score: float                  # ngưỡng score tối thiểu

    # --- Accumulates qua mỗi iteration (reducer: append) ---
    all_memories: Annotated[list[dict[str, Any]], operator.add]
    search_queries: Annotated[list[str], operator.add]   # track queries đã dùng

    # --- Per-iteration (overwrite mỗi vòng) ---
    current_query: str
    iteration: int
    max_iterations: int

    # --- Judge output ---
    verdict: dict[str, Any]
    # {
    #   "sufficient": bool,
    #   "reason": str,           # "low_score" | "low_coverage" | "contradictions" | "ok"
    #   "missing_aspects": str,  # "chưa có thông tin về token refresh"
    #   "next_query": str,       # query refined cho iteration tiếp theo
    #   "confidence": float,
    # }

    # --- Final output ---
    final_memories: list[dict[str, Any]]
    recall_summary: str
```

**Graph nodes**:

```
[recall_node] → [judge_node] → sufficient? ──YES──→ [merge_node] → END
                     │
                    NO (và iteration < max)
                     ↓
               [refine_node] → [recall_node]  (loop)
```

**recall_node**: Thực hiện vector search + BM25 + compatibility scoring với `current_query`. Kết quả append vào `all_memories` nhờ reducer `operator.add`.

**judge_node**: Gọi LLM local với prompt:

```
Bạn là judge đánh giá chất lượng retrieved memories.
Query gốc: {original_query}
Workflow step: {current_step}
Memories tìm được: {all_memories}

Đánh giá:
1. Có đủ thông tin để trả lời query không?
2. Score trung bình có >= {min_score} không?
3. Có gaps nào quan trọng chưa được cover?
4. Nếu chưa đủ, query tiếp theo nên là gì?

Output JSON: {"sufficient": bool, "reason": str, "missing_aspects": str, "next_query": str, "confidence": float}
```

**Routing**: `sufficient OR iteration >= max_iterations → merge_node`, ngược lại → `refine_node`.

**refine_node**: Đọc `verdict.next_query`, set `current_query = next_query`, tăng `iteration`.

**merge_node**: Dedup `all_memories` theo ID, sort by score, take `target_count` tốt nhất, gọi `ContinuitySynthesizer` lần cuối.

**Tích hợp vào `minder_memory_recall`**:

```python
# memory.py — minder_memory_recall
async def minder_memory_recall(self, query, *, limit=5, current_step=None, ...):
    if self._use_agentic_loop():  # config flag: config.memory.agentic_recall
        return await self._agentic_recall(query, limit=limit, current_step=current_step)
    # fallback: code cũ giữ nguyên
    ...

async def _agentic_recall(self, query, limit, current_step):
    graph = AgenticMemoryGraph(
        memory_tools=self,
        llm=self._llm,          # local LLM cho judge
        config=self._config,
    )
    result = await graph.run(MemoryRecallState(
        original_query=query,
        current_query=query,
        target_count=limit,
        min_score=self._config.memory.recall_min_score,  # default: 0.4
        max_iterations=self._config.memory.recall_max_iterations,  # default: 3
        current_step=current_step,
        ...
    ))
    return result["final_memories"]
```

**Config mới**:

```toml
# minder.toml
[memory]
agentic_recall = true
recall_min_score = 0.4
recall_max_iterations = 3
```

---

### 0B. SessionContextGraph

**Mục tiêu**: `minder_session_restore` không chỉ load session mà còn tự động kéo memories đúng phase và validate coherence.

**State**:

```python
class SessionRestoreState(TypedDict):
    session_id: str

    # Loaded từ DB
    session_state: dict[str, Any]
    workflow_step: str | None
    workflow_context: dict[str, Any]
    project_context: dict[str, Any]

    # Memories tìm được (targeted theo step)
    recalled_memories: list[dict[str, Any]]

    # Coherence check
    coherence_result: dict[str, Any]
    # {
    #   "coherent": bool,
    #   "contradictions": list[str],   # ["session nói dùng JWT, memory nói dùng cookie"]
    #   "stale_memories": list[str],   # memory IDs có thể đã outdated
    #   "confidence": float,
    # }

    # Final unified context
    unified_context: dict[str, Any]
```

**Graph pipeline**:

```
[load_session] → [targeted_recall] → [coherence_check] → [build_context] → END
                                           │
                              contradictions found?
                                           ↓
                                   [resolve_conflicts]  (LLM pick winner)
                                           ↓
                                   [build_context]
```

**targeted_recall**: Không dùng query tổng quát. Tự động tạo query từ session state:

```python
def build_targeted_queries(session_state, workflow_step) -> list[str]:
    queries = []
    task = session_state.get("task", "")
    if task:
        queries.append(f"{task} {workflow_step or ''}")
    if workflow_step:
        queries.append(f"best practices for {workflow_step} phase")
        queries.append(f"artifacts required in {workflow_step}")
    return queries[:3]  # max 3 queries
```

Gọi `AgenticMemoryGraph` với mỗi query này, merge kết quả.

**coherence_check**: LLM judge kiểm tra:

- Session nói `task = "fix JWT expiry bug"` — memory có mention JWT không? → OK
- Session nói `step = "implement"` — memory nào là về "design phase" có thể stale?
- Contradictions: session `branch=fix/auth-v2` nhưng memory về `auth-v1`

**build_context**: Tạo unified context thay thế 3 calls rời:

```python
{
    "session_id": "...",
    "state": {...},                         # từ session
    "workflow_step": "implement",
    "relevant_memories": [...],             # memories đã được judge + coherence check
    "continuity_packet": {...},             # từ build_instruction_envelope hiện tại
    "coherence_warnings": ["..."],          # để Claude biết có mâu thuẫn
    "context_confidence": 0.87,             # độ tin cậy của toàn bộ context
}
```

**Tích hợp vào `minder_session_restore`**:

```python
async def minder_session_restore(self, session_id):
    if self._config.session.agentic_restore:
        graph = SessionContextGraph(session_tools=self, memory_tools=self._memory_tools, ...)
        return await graph.run(SessionRestoreState(session_id=str(session_id)))
    # fallback: code cũ
    ...
```

---

## Phase 1: GraphState TypedDict + Annotated Reducers

**Mục tiêu**: Chuyển `GraphState` sang TypedDict với reducers — prerequisite cho parallel execution.

**Files sửa**:

- `src/minder/graph/state.py` — **REFACTOR**
- `src/minder/graph/executor.py` — cập nhật type hints
- `tests/graph/test_state.py` — cập nhật tests

**Thay đổi**:

```python
# TRƯỚC (Pydantic BaseModel)
class GraphState(BaseModel):
    retrieved_docs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

# SAU (TypedDict + Annotated reducers)
import operator
from typing import Annotated, TypedDict

class GraphState(TypedDict):
    # Parallel-safe: mỗi node append, không overwrite
    retrieved_docs: Annotated[list[dict[str, Any]], operator.add]
    reranked_docs: Annotated[list[dict[str, Any]], operator.add]

    # Dict merge reducer (không replace)
    metadata: Annotated[dict[str, Any], lambda a, b: {**a, **b}]

    # Fields không cần reducer (chỉ 1 node write)
    query: str
    session_id: str | None
    repo_path: str | None
    plan: dict[str, Any]
    llm_output: dict[str, Any]
    workflow_context: dict[str, Any]
    guard_result: dict[str, Any]
    verification_result: dict[str, Any]
    evaluation: dict[str, Any]
    retry_count: int
    chat_history: list[dict[str, Any]]
    transition_log: Annotated[list[dict[str, Any]], operator.add]
```

**Breaking change risk**: Thấp — `GraphState` được tạo và đọc trong nội bộ graph. MCP tool callers không expose trực tiếp. Cần audit `GraphState.model_validate()` calls → replace bằng `GraphState(**data)`.

**Validation**: Chạy `tests/graph/` sau khi sửa.

---

## Phase 2: MongoDB Checkpointer

**Mục tiêu**: LangGraph checkpoint backed by Minder's `IOperationalStore` — workflow resume sau crash, human-in-the-loop trong Phase 5.

**Files tạo**:

- `src/minder/graph/checkpoint.py` — **TẠO MỚI**

**Files sửa**:

- `src/minder/store/interfaces.py` — thêm `get_checkpoint`, `save_checkpoint`
- `src/minder/store/mongodb/operational.py` — implement checkpoint methods
- `src/minder/store/relational.py` — implement checkpoint methods (SQLite fallback)
- `src/minder/graph/graph.py` — inject checkpointer vào compiled graph

**Schema checkpoint trong DB**:

```
Collection: minder_checkpoints
{
  thread_id: string,       # = session_id
  checkpoint_id: string,   # LangGraph internal
  checkpoint: bytes,       # serialized checkpoint
  metadata: dict,
  created_at: datetime,
}
```

**Implementation**:

```python
# src/minder/graph/checkpoint.py
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointTuple

class MinderCheckpointSaver(BaseCheckpointSaver):
    def __init__(self, store: IOperationalStore) -> None:
        super().__init__()
        self._store = store

    async def aget_tuple(self, config: dict) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        data = await self._store.get_checkpoint(thread_id)
        if data is None:
            return None
        return CheckpointTuple(
            config=config,
            checkpoint=self.serde.loads(data["checkpoint"]),
            metadata=data.get("metadata", {}),
        )

    async def aput(self, config, checkpoint, metadata, new_versions) -> dict:
        thread_id = config["configurable"]["thread_id"]
        await self._store.save_checkpoint(
            thread_id=thread_id,
            checkpoint_id=checkpoint["id"],
            checkpoint=self.serde.dumps(checkpoint),
            metadata=metadata,
        )
        return config

    async def alist(self, config, *, filter=None, before=None, limit=None):
        # Cho phép list checkpoints của một thread
        thread_id = config["configurable"]["thread_id"]
        records = await self._store.list_checkpoints(thread_id, limit=limit or 10)
        for record in records:
            yield CheckpointTuple(
                config={"configurable": {"thread_id": thread_id, "checkpoint_id": record["checkpoint_id"]}},
                checkpoint=self.serde.loads(record["checkpoint"]),
                metadata=record.get("metadata", {}),
            )
```

**Inject vào MinderGraph**:

```python
# graph/graph.py
class MinderGraph:
    def __init__(self, store, config):
        self._checkpointer = MinderCheckpointSaver(store)
        self._compiled = self._build().compile(checkpointer=self._checkpointer)

    async def run(self, state: GraphState, *, session_id: str | None = None) -> GraphState:
        config = {"configurable": {"thread_id": session_id or "default"}}
        return await self._compiled.ainvoke(state, config)
```

**Lợi ích ngay**: `minder_query` với `session_id` → workflow có thể resume sau crash.

---

## Phase 3: Parallel Retrieval với Send API

**Mục tiêu**: Fan out 3 chiến lược retrieval (vector, BM25, knowledge graph) chạy đồng thời, merge lại.

**Files tạo**:

- `src/minder/graph/nodes/parallel_retriever.py` — **TẠO MỚI**

**Files sửa**:

- `src/minder/graph/executor.py` — thay `retriever` node bằng parallel fan-out
- `src/minder/graph/nodes/__init__.py` — export `ParallelRetrieverNode`

**Graph thay đổi** (trong `LangGraphExecutorAdapter._build_compiled_graph`):

```python
from langgraph.types import Send

def plan_retrieval(state: GraphState) -> list[Send]:
    strategies = [
        {"strategy": "vector",          "alpha": 1.0},
        {"strategy": "bm25",            "alpha": 0.0},
        {"strategy": "knowledge_graph", "alpha": 0.5},
    ]
    return [Send("retrieve_strategy", {**state, "metadata": {**state["metadata"], **s}})
            for s in strategies]

# Add nodes
workflow.add_node("plan_retrieval", plan_retrieval)
workflow.add_node("retrieve_strategy", retrieve_strategy_node)
workflow.add_node("merge_retrieved", merge_results_node)

# Fan-out edges
workflow.add_conditional_edges("plan_retrieval", plan_retrieval, ["retrieve_strategy"])
workflow.add_edge("retrieve_strategy", "merge_retrieved")

# Sau merge, chạy reranker hoặc reasoning như cũ
workflow.add_edge("merge_retrieved", "reranker" if nodes.reranker else "reasoning")
```

**retrieve_strategy_node**:

```python
async def retrieve_strategy_node(state: GraphState) -> GraphState:
    strategy = state["metadata"].get("strategy", "vector")
    docs = []

    if strategy == "vector":
        docs = await vector_store.search_documents(embed(state["query"]), ...)
        for d in docs:
            d["retrieval_strategy"] = "vector"

    elif strategy == "bm25":
        docs = bm25_search(state["query"], corpus=all_docs)
        for d in docs:
            d["retrieval_strategy"] = "bm25"

    elif strategy == "knowledge_graph":
        docs = await graph_store.traverse_by_query(state["query"], ...)
        for d in docs:
            d["retrieval_strategy"] = "knowledge_graph"

    # Annotated[list, operator.add] → tự động APPEND vào state chung
    return {"retrieved_docs": docs}
```

**merge_results_node**:

```python
async def merge_results_node(state: GraphState) -> GraphState:
    # retrieved_docs đã có docs từ cả 3 strategies nhờ reducer
    hybrid = HybridRetriever(alpha=config.retrieval.hybrid_alpha)
    merged = hybrid.merge(
        state["query"],
        vector_results=[d for d in state["retrieved_docs"] if d.get("retrieval_strategy") == "vector"],
        corpus=state["retrieved_docs"],
        limit=config.retrieval.rerank_top_n,
    )
    return {"reranked_docs": merged, "retrieved_docs": []}  # clear raw, keep merged
```

**Chỉ áp dụng cho LangGraphExecutorAdapter** — `InternalGraphExecutor` giữ nguyên tuần tự.

---

## Phase 4: Native Streaming với `astream_events`

**Mục tiêu**: Thay custom event loop trong `minder_query_stream` bằng LangGraph's `astream_events` — UX improvement cho SSE clients.

**Files sửa**:

- `src/minder/tools/query.py` — `minder_query_stream`
- `src/minder/graph/graph.py` — expose `astream_events`

**Thay đổi**:

```python
# query.py — minder_query_stream
async def minder_query_stream(self, query, *, session_id=None, ...):
    config = {"configurable": {"thread_id": str(session_id) if session_id else "default"}}
    state = GraphState(query=query, ...)

    async for event in self._graph.astream_events(state, config, version="v2"):
        event_name = event["event"]

        if event_name == "on_chain_start":
            # Node bắt đầu chạy
            yield {"type": "node_start", "node": event["name"], "input": None}

        elif event_name == "on_chat_model_stream":
            # Token-level streaming từ LLM
            chunk = event["data"].get("chunk", {})
            yield {"type": "token", "delta": getattr(chunk, "content", "")}

        elif event_name == "on_chain_end" and event["name"] == "merge_retrieved":
            # Retrieval xong → gửi sources sớm cho UX
            output = event["data"].get("output", {})
            docs = output.get("reranked_docs", [])
            yield {"type": "sources", "sources": [{"path": d["path"], "score": d["score"]} for d in docs[:5]]}

        elif event_name == "on_chain_end" and event["name"] in {"evaluator", "reflection"}:
            # Final result
            final = event["data"].get("output", {})
            yield {"type": "final", "payload": self._result_from_state(GraphState(**final))}
```

**Event sequence cho SSE client**:

```
→ {type: "node_start", node: "plan_retrieval"}
→ {type: "node_start", node: "retrieve_strategy"}  (3 lần, parallel)
→ {type: "sources", sources: [...]}                 (sau merge_retrieved)
→ {type: "node_start", node: "llm"}
→ {type: "token", delta: "The"}
→ {type: "token", delta: " authentication"}
→ {type: "token", delta: " flow..."}
→ {type: "final", payload: {...}}
```

---

## Phase 5: Human-in-the-Loop với `interrupt()`

**Mục tiêu**: `minder_workflow_guard` dùng LangGraph's `interrupt()` — thực sự dừng và resume thay vì boolean check.

**Điều kiện**: Phase 2 (Checkpointer) phải done trước.

**Files sửa**:

- `src/minder/graph/nodes/guard.py` — thêm `interrupt()`
- `src/minder/tools/workflow.py` — `minder_workflow_step` resume
- `src/minder/graph/graph.py` — compile với `interrupt_before`

**Guard node**:

```python
# graph/nodes/guard.py
from langgraph.types import interrupt

async def run(self, state: GraphState) -> GraphState:
    # Check hiện tại giữ nguyên
    guard_result = self._evaluate(state)

    requires_human = (
        state.workflow_context.get("requires_human_approval", False)
        or guard_result.get("severity") == "high"
    )

    if requires_human:
        # LangGraph lưu checkpoint TẠI ĐÂY, trả về caller ngay
        decision = interrupt({
            "type": "approval_required",
            "session_id": str(state.session_id),
            "workflow_step": state.workflow_context.get("current_step"),
            "artifact_preview": state.llm_output.get("text", "")[:500],
            "guard_reasons": guard_result.get("reasons", []),
        })
        # Resume khi human gọi minder_workflow_step với decision
        if not decision.get("approved", False):
            return {**state, "guard_result": {**guard_result, "human_rejected": True}}

    return {**state, "guard_result": guard_result}
```

**Compile**:

```python
compiled = workflow.compile(
    checkpointer=self._checkpointer,
    interrupt_before=["guard"],  # dừng TRƯỚC guard cho high-risk actions
)
```

**Resume trong minder_workflow_step**:

```python
# tools/workflow.py
from langgraph.types import Command

async def minder_workflow_step(self, session_id, *, decision: dict) -> dict:
    config = {"configurable": {"thread_id": str(session_id)}}
    # Inject human decision vào interrupt() point
    result = await self._compiled_graph.ainvoke(
        Command(resume=decision),
        config,
    )
    return {"status": "resumed", "edge": determine_next_edge(GraphState(**result))}
```

**Flow thực tế**:

```
minder_query("deploy service X to prod")
  → guard node: interrupt()
  → return {status: "waiting_approval", session_id: "abc123"}

# Human review artifact, sau đó:
minder_workflow_step(session_id="abc123", decision={"approved": True, "comment": "LGTM"})
  → resume từ guard node
  → continue: verification → evaluator → END
```

---

## Phase 6: Multi-Agent SubGraph với Supervisor

**Mục tiêu**: Mỗi `SubAgent` từ DB compile thành LangGraph subgraph độc lập. Supervisor routing dùng `Send` API.

**Điều kiện**: Phase 1-3 phải done.

**Files tạo**:

- `src/minder/graph/supervisor.py` — **TẠO MỚI**

**Files sửa**:

- `src/minder/tools/agents.py` — thêm subgraph compilation
- `src/minder/bootstrap/transport.py` — init AgentSupervisor

**AgentSupervisor**:

```python
# graph/supervisor.py
class AgentSupervisor:
    def __init__(self, store, nodes: GraphNodes, config):
        self._store = store
        self._nodes = nodes
        self._config = config
        self._agent_graphs: dict[str, Any] = {}  # cache compiled subgraphs

    async def build_subgraph(self, agent: SubAgentSchema) -> Any:
        """Compile SubAgent thành StateGraph độc lập."""
        sg = StateGraph(GraphState)

        sg.add_node("inject_context", lambda s: {
            **s,
            "metadata": {
                **s["metadata"],
                "system_prompt": agent.system_prompt,
                "agent_name": agent.name,
            }
        })

        # Chỉ add nodes mà agent này cần (theo agent.tools)
        node_map = {
            "minder_search_code": ("retriever", self._nodes.retriever.run),
            "minder_query": ("llm", self._nodes.llm.run),
            "minder_memory_recall": ("memory_recall", self._memory_node),
        }
        last_node = "inject_context"
        for tool_name in agent.tools:
            if tool_name in node_map:
                node_id, node_fn = node_map[tool_name]
                sg.add_node(node_id, node_fn)
                sg.add_edge(last_node, node_id)
                last_node = node_id

        sg.set_entry_point("inject_context")
        sg.add_edge(last_node, END)
        return sg.compile()

    def supervisor_router(self, state: GraphState) -> list[Send]:
        """Route query đến đúng agent(s), có thể parallel."""
        intent = state["plan"].get("intent", "")
        tags = state["plan"].get("required_agents", [])

        sends = []
        for agent_name in tags:
            if agent_name in self._agent_graphs:
                sends.append(Send(f"agent_{agent_name}", state))

        # Fallback: default agent
        if not sends and "default" in self._agent_graphs:
            sends.append(Send("agent_default", state))

        return sends
```

**Multi-agent graph**:

```python
# graph/graph.py — khi có supervisor
multi_agent = StateGraph(GraphState)
multi_agent.add_node("planning", self._nodes.planning.run)
multi_agent.add_node("supervisor", supervisor.supervisor_router)

# Add mỗi agent là 1 node (subgraph)
for agent in loaded_agents:
    subgraph = await supervisor.build_subgraph(agent)
    multi_agent.add_node(f"agent_{agent.name}", subgraph)

multi_agent.add_node("aggregator", merge_agent_outputs)  # merge parallel outputs
```

---

## Implementation Order

```
Phase 0A  AgenticMemoryGraph         Independent, can start immediately
Phase 0B  SessionContextGraph        Independent, can start immediately
    ↓
Phase 1   GraphState TypedDict       Foundation, no breaking changes
    ↓
Phase 2   MongoDB Checkpointer       Required before Phase 5
    ↓
Phase 3   Parallel Retrieval         Requires Phase 1
    ↓
Phase 4   astream_events             Requires Phase 2 config
    ↓
Phase 5   Human-in-the-loop          Requires Phase 2 checkpointer
    ↓
Phase 6   Multi-agent SubGraph       Requires Phases 1, 2, and 3
```

---

## Additional Config

```toml
# minder.toml

[memory]
agentic_recall = true             # bật agentic loop trong minder_memory_recall
recall_min_score = 0.4            # ngưỡng score tối thiểu
recall_max_iterations = 3         # số vòng lặp tối đa

[session]
agentic_restore = true            # bật pipeline trong minder_session_restore
restore_recall_count = 8          # số memories kéo về khi restore

[graph]
runtime = "langgraph"             # "langgraph" | "internal"
enable_parallel_retrieval = true  # bật Phase 3
enable_checkpointing = true       # bật Phase 2
checkpoint_ttl_days = 7           # TTL cho checkpoint records
```

---

## Test coverage cho mỗi Phase

| Phase | Test file                                | Test cases                                         |
| ----- | ---------------------------------------- | -------------------------------------------------- |
| 0A    | `tests/graph/test_memory_graph.py`       | loop terminates, judge fires, dedup hoạt động      |
| 0B    | `tests/graph/test_session_graph.py`      | coherence detection, targeted queries              |
| 1     | `tests/graph/test_state.py`              | reducers merge đúng, parallel write không conflict |
| 2     | `tests/graph/test_checkpoint.py`         | save/restore checkpoint, thread isolation          |
| 3     | `tests/graph/test_parallel_retriever.py` | 3 strategies chạy song song, merge đúng            |
| 4     | `tests/tools/test_query_stream.py`       | events đúng order, sources event trước final       |
| 5     | `tests/graph/test_interrupt.py`          | interrupt dừng đúng, resume với decision           |
| 6     | `tests/graph/test_supervisor.py`         | routing đúng agent, parallel subgraphs             |

---

## Ghi chú

- **Backward compatibility**: Mỗi phase đều có config flag để rollback. `InternalGraphExecutor` giữ nguyên, không xóa.
- **LLM judge trong Phase 0**: Dùng cùng LLM factory (`llm/factory.py`) — không cần dependency mới. Nếu LLM unavailable → fallback heuristic (score threshold check).
- **Phase 0 không cần Phase 1-6**: `AgenticMemoryGraph` và `SessionContextGraph` dùng LangGraph StateGraph trực tiếp với Pydantic state riêng — không depend vào `GraphState` hiện tại.
