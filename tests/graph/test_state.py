from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from minder.graph.state import GraphStateSchema


def test_graph_state_schema_reducers_merge_parallel_updates() -> None:
    def node_a(state: GraphStateSchema) -> dict:
        del state
        return {
            "retrieved_docs": [{"path": "a.py", "score": 0.9}],
            "metadata": {"a": True},
            "transition_log": [{"edge": "a"}],
        }

    def node_b(state: GraphStateSchema) -> dict:
        del state
        return {
            "retrieved_docs": [{"path": "b.py", "score": 0.8}],
            "metadata": {"b": True},
            "transition_log": [{"edge": "b"}],
        }

    graph = StateGraph(GraphStateSchema)
    graph.add_node("node_a", node_a)
    graph.add_node("node_b", node_b)
    graph.add_edge(START, "node_a")
    graph.add_edge(START, "node_b")
    graph.add_edge("node_a", END)
    graph.add_edge("node_b", END)
    compiled = graph.compile()

    result = compiled.invoke({"query": "test", "metadata": {}, "retrieved_docs": [], "transition_log": []})

    assert {doc["path"] for doc in result["retrieved_docs"]} == {"a.py", "b.py"}
    assert result["metadata"] == {"a": True, "b": True}
    assert {item["edge"] for item in result["transition_log"]} == {"a", "b"}
