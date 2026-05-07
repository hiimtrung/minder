from __future__ import annotations

from collections.abc import Awaitable, Callable
import inspect
from typing import TYPE_CHECKING, Any

from minder.config import MinderConfig
from minder.graph.runtime import load_langgraph_state_graph
from minder.graph.state import GraphState, GraphStateSchema
from minder.store.interfaces import IOperationalStore

if TYPE_CHECKING:
    from minder.graph.executor import GraphNodes


class AgentSupervisor:
    def __init__(
        self,
        store: IOperationalStore,
        nodes: GraphNodes,
        config: MinderConfig | None = None,
        *,
        graph_tools: Any | None = None,
    ) -> None:
        self._store = store
        self._nodes = nodes
        self._config = config
        self._graph_tools = graph_tools
        self._agent_graphs: dict[str, Any] = {}
        self._agent_defs: dict[str, dict[str, Any]] = {}

    @property
    def has_agents(self) -> bool:
        return bool(self._agent_graphs)

    def destinations(self) -> list[str]:
        return [f"agent_{name}" for name in self._agent_graphs]

    async def initialize(self) -> None:
        agents = await self._store.list_agents()
        for agent in agents:
            payload = self._serialize_agent(agent)
            name = payload["name"]
            if not name:
                continue
            self._agent_defs[name] = payload
            self._agent_graphs[name] = await self.build_subgraph(payload)

    async def build_subgraph(self, agent: dict[str, Any]) -> Any:
        state_graph_cls = load_langgraph_state_graph()
        if state_graph_cls is None:
            raise RuntimeError("LangGraph runtime requested but StateGraph is unavailable")
        workflow = state_graph_cls(GraphStateSchema)

        workflow.add_node(
            "inject_context", self._wrap_state_handler(self._build_inject_context(agent))
        )
        last_node = "inject_context"

        if self._agent_needs_retrieval(agent):
            workflow.add_node("retriever", self._wrap_state_handler(self._nodes.retriever.run))
            last_node = self._add_edge_and_return(workflow, last_node, "retriever")
            if self._nodes.reranker is not None:
                workflow.add_node(
                    "reranker", self._wrap_state_handler(self._nodes.reranker.run)
                )
                last_node = self._add_edge_and_return(workflow, last_node, "reranker")

        workflow.add_node("reasoning", self._wrap_state_handler(self._nodes.reasoning.run))
        workflow.add_node("llm", self._wrap_state_handler(self._nodes.llm.run))
        workflow.add_edge(last_node, "reasoning")
        workflow.add_edge("reasoning", "llm")
        workflow.set_entry_point("inject_context")
        workflow.add_edge("llm", "__end__")
        return workflow.compile()

    def make_agent_node(self, agent_name: str) -> Callable[[GraphState], Awaitable[dict[str, Any]]]:
        compiled = self._agent_graphs[agent_name]
        definition = self._agent_defs[agent_name]

        async def run_agent(state: GraphState) -> dict[str, Any]:
            agent_state = (
                state
                if isinstance(state, GraphState)
                else GraphState.model_validate(state)
            ).model_copy(deep=True)
            result = await compiled.ainvoke(agent_state.model_dump(mode="python"))
            result_state = (
                result if isinstance(result, GraphState) else GraphState.model_validate(result)
            )
            docs = list(result_state.reranked_docs or result_state.retrieved_docs or [])
            return {
                "agent_outputs": [
                    {
                        "agent_name": agent_name,
                        "llm_output": dict(result_state.llm_output),
                        "reasoning_output": dict(result_state.reasoning_output),
                        "retrieved_docs": docs,
                        "metadata": {
                            "title": definition.get("title"),
                            "workflow_steps": list(definition.get("workflow_steps", []) or []),
                            "artifact_types": list(definition.get("artifact_types", []) or []),
                            "tags": list(definition.get("tags", []) or []),
                            "is_default": bool(definition.get("is_default", False)),
                        },
                    }
                ]
            }

        return run_agent

    @staticmethod
    def supervisor_entry(state: GraphState) -> GraphState:
        return state

    def supervisor_router(self, state: GraphState) -> list[Any] | str:
        from langgraph.types import Send

        selected = self._select_agent_names(state)
        if not selected:
            return "fallback_retrieval"
        payload = state.model_dump(mode="python")
        return [Send(f"agent_{name}", payload) for name in selected if name in self._agent_graphs]

    def aggregate_agent_outputs(self, state: GraphState) -> GraphState:
        outputs = list(state.agent_outputs or [])
        if not outputs:
            state.metadata["supervisor_used"] = False
            return state

        required_agents = list(state.plan.get("required_agents", []) or [])
        selected_output = None
        for required in required_agents:
            selected_output = next(
                (item for item in outputs if item.get("agent_name") == required),
                None,
            )
            if selected_output is not None:
                break
        if selected_output is None:
            selected_output = max(outputs, key=self._agent_output_rank)

        docs = list(selected_output.get("retrieved_docs", []) or [])
        state.llm_output = dict(selected_output.get("llm_output", {}) or {})
        state.reasoning_output = dict(selected_output.get("reasoning_output", {}) or {})
        state.reranked_docs = docs
        state.agent_outputs = []
        state.metadata["supervisor_used"] = True
        state.metadata["supervisor_selected_agent"] = selected_output.get("agent_name")
        state.metadata["supervisor_agents"] = [
            item.get("agent_name") for item in outputs if item.get("agent_name")
        ]
        return state

    def _select_agent_names(self, state: GraphState) -> list[str]:
        selected: list[str] = []
        required = [str(item) for item in list(state.plan.get("required_agents", []) or []) if str(item)]
        selected.extend([name for name in required if name in self._agent_defs])

        workflow_step = str(state.workflow_context.get("current_step", "") or "")
        if not selected and workflow_step:
            lowered_step = workflow_step.lower()
            for name, payload in self._agent_defs.items():
                steps = [str(step).lower() for step in list(payload.get("workflow_steps", []) or [])]
                if lowered_step in steps:
                    selected.append(name)

        if not selected:
            selected.extend(
                name
                for name, payload in self._agent_defs.items()
                if bool(payload.get("is_default", False))
            )

        seen: set[str] = set()
        ordered: list[str] = []
        for name in selected:
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    @staticmethod
    def _agent_output_rank(output: dict[str, Any]) -> tuple[int, int, int]:
        metadata = dict(output.get("metadata", {}) or {})
        docs = list(output.get("retrieved_docs", []) or [])
        text = str(dict(output.get("llm_output", {}) or {}).get("text", "") or "")
        return (
            1 if bool(metadata.get("is_default", False)) else 0,
            len(docs),
            len(text),
        )

    @staticmethod
    def _serialize_agent(agent: Any) -> dict[str, Any]:
        return {
            "name": str(getattr(agent, "name", "") or ""),
            "title": str(getattr(agent, "title", "") or ""),
            "description": str(getattr(agent, "description", "") or ""),
            "system_prompt": str(getattr(agent, "system_prompt", "") or ""),
            "tools": list(getattr(agent, "tools", []) or []),
            "workflow_steps": list(getattr(agent, "workflow_steps", []) or []),
            "artifact_types": list(getattr(agent, "artifact_types", []) or []),
            "tags": list(getattr(agent, "tags", []) or []),
            "is_default": bool(getattr(agent, "is_default", False)),
        }

    @staticmethod
    def _build_inject_context(agent: dict[str, Any]) -> Callable[[GraphState], GraphState]:
        def inject_context(state: GraphState) -> GraphState:
            state.metadata["agent_name"] = agent["name"]
            state.metadata["agent_system_prompt"] = agent["system_prompt"]
            state.workflow_context["agent"] = {
                "name": agent["name"],
                "title": agent["title"],
                "tools": list(agent.get("tools", []) or []),
            }
            return state

        return inject_context

    @staticmethod
    def _agent_needs_retrieval(agent: dict[str, Any]) -> bool:
        retrieval_tools = {
            "minder_search_code",
            "minder_search_graph",
            "minder_find_impact",
            "minder_search_errors",
            "minder_memory_recall",
            "minder_skill_recall",
        }
        tools = {str(item) for item in list(agent.get("tools", []) or []) if str(item)}
        return bool(retrieval_tools & tools)

    @staticmethod
    def _add_edge_and_return(workflow: Any, source: str, dest: str) -> str:
        workflow.add_edge(source, dest)
        return dest

    @staticmethod
    def _wrap_state_handler(handler):  # noqa: ANN001
        async def wrapped(state):  # noqa: ANN001
            graph_state = GraphState.model_validate(state)
            result = handler(graph_state)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, GraphState):
                return result.model_dump(mode="python")
            return result

        return wrapped
