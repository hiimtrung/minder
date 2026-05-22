import pytest

from minder.config import MinderConfig, GraphConfig, WorkflowConfig
from minder.graph.state import GraphState
from minder.tools.query import QueryTools
from minder.store.relational import RelationalStore


class MockLangGraph:
    async def astream_events(self, state: GraphState, config: dict, version="v2"):
        # simulate events
        yield {"event": "on_chain_start", "name": "reasoning"}
        yield {"event": "on_chat_model_stream", "name": "llm", "data": {"chunk": type("Chunk", (), {"content": "hello"})()}}
        yield {"event": "on_chain_end", "name": "merge_retrieved", "data": {"output": {"reranked_docs": [{"path": "file1.py", "score": 0.9}]}}}
        yield {"event": "on_chain_end", "name": "LangGraph", "data": {"output": {"query": state.query, "llm_output": {"text": "hello"}}}}


class MockGraph:
    def __init__(self, runtime="langgraph"):
        self.runtime = runtime
        if runtime == "langgraph":
            self.astream_events = MockLangGraph().astream_events
        else:
            self.stream = self._internal_stream
            
    async def _internal_stream(self, state: GraphState):
        yield {"type": "final", "state": GraphState(query=state.query, llm_output={"text": "fallback"})}


@pytest.fixture
async def store() -> RelationalStore:
    store = RelationalStore("sqlite+aiosqlite:///:memory:")
    await store.init_db()
    return store


@pytest.mark.asyncio
async def test_minder_query_stream_langgraph(store: RelationalStore):
    config = MinderConfig()
    config.graph = GraphConfig(runtime="langgraph")
    config.workflow = WorkflowConfig(orchestration_runtime="langgraph")

    graph = MockGraph(runtime="langgraph")
    tools = QueryTools(store, config, graph=graph)
    
    events = []
    async for event in tools.minder_query_stream("test query", repo_path=None):
        events.append(event)
        
    assert len(events) == 4
    assert events[0] == {"type": "attempt", "attempt": 1}
    assert events[1] == {"type": "chunk", "attempt": 1, "delta": "hello"}
    assert events[2] == {"type": "sources", "sources": [{"path": "file1.py", "score": 0.9}]}
    assert events[3]["type"] == "final"
    assert events[3]["payload"]["answer"] == "hello"


@pytest.mark.asyncio
async def test_minder_query_stream_internal(store: RelationalStore):
    config = MinderConfig()
    config.graph = GraphConfig(runtime="internal")
    config.workflow = WorkflowConfig(orchestration_runtime="internal")

    graph = MockGraph(runtime="internal")
    tools = QueryTools(store, config, graph=graph)
    
    events = []
    async for event in tools.minder_query_stream("test query", repo_path=None):
        events.append(event)
        
    assert len(events) == 1
    assert events[0]["type"] == "final"
    assert events[0]["payload"]["answer"] == "fallback"
