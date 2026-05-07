import asyncio
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

class State(TypedDict):
    query: str
    output: str

def node1(state: State):
    return {"output": "hello"}

workflow = StateGraph(State)
workflow.add_node("node1", node1)
workflow.add_edge(START, "node1")
workflow.add_edge("node1", END)
app = workflow.compile()

async def main():
    async for event in app.astream_events({"query": "hi"}, version="v2"):
        if event["event"] == "on_chain_end":
            print(event["name"], event["data"]["output"])

asyncio.run(main())
