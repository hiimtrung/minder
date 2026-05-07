import asyncio
import operator
from typing import Annotated, Any

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END


def merge_dicts(a: dict, b: dict) -> dict:
    res = dict(a or {})
    res.update(b or {})
    return res


class MyState(BaseModel):
    query: str
    docs: Annotated[list[str], operator.add] = Field(default_factory=list)
    metadata: Annotated[dict[str, Any], merge_dicts] = Field(default_factory=dict)


def node1(state: MyState) -> dict:
    print(type(state))
    return {"docs": ["doc1"], "metadata": {"node1": True}}


def node2(state: MyState) -> dict:
    print(type(state))
    return {"docs": ["doc2"], "metadata": {"node2": True}}


async def main():
    graph = StateGraph(MyState)
    graph.add_node("node1", node1)
    graph.add_node("node2", node2)

    graph.add_edge(START, "node1")
    graph.add_edge(START, "node2")
    graph.add_edge("node1", END)
    graph.add_edge("node2", END)

    compiled = graph.compile()
    
    state = MyState(query="test")
    res = await compiled.ainvoke(state)
    print("Result:", res)


if __name__ == "__main__":
    asyncio.run(main())
