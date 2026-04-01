"""Created: 2026-03-31

Purpose: Implements the reusable ReAct graph assembler for shared agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.agents.nodes import MemoryRetrieveNode, ReactNode, ReActState, ReflectNode, ResponseNode, SessionStoreProtocol, ToolExecutionNode
from src.memory.base import BaseMemoryStore
from src.tools.executor import ToolExecutor


@dataclass(slots=True)
class ReActAgent:
    planner: Any
    executor: ToolExecutor
    session_store: SessionStoreProtocol
    memory_store: BaseMemoryStore | None = None
    memory_retriever: Any | None = None
    agent_name: str = "platform"
    _graph: Any = field(init=False, repr=False)
    _memory_retrieve_step: MemoryRetrieveNode = field(init=False, repr=False)
    _react_step: ReactNode = field(init=False, repr=False)
    _tool_step: ToolExecutionNode = field(init=False, repr=False)
    _reflect_step: ReflectNode = field(init=False, repr=False)
    _response_step: ResponseNode = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._memory_retrieve_step = MemoryRetrieveNode(
            tool_registry=self.executor.registry,
            planner=self.planner,
            memory_retriever=self.memory_retriever,
        )
        self._react_step = ReactNode(planner=self.planner)
        self._tool_step = ToolExecutionNode(executor=self.executor)
        self._reflect_step = ReflectNode(memory_store=self.memory_store, agent_name=self.agent_name)
        self._response_step = ResponseNode()
        self._graph = self._build_graph()

    def run(self, user_input: str, session_id: str) -> str:
        memory = self.session_store.load(session_id)
        memory.add_user_message(user_input)
        state = self._graph.invoke(
            {
                "user_input": user_input,
                "memory": memory,
                "observation": None,
                "steps": 0,
            }
        )
        response = state.get("response", "I’m not sure what to do next.")
        memory.add_agent_message(response)
        return response

    def _build_graph(self) -> Any:
        graph = StateGraph(ReActState)
        graph.add_node("retrieve_memory", self._memory_retrieve_step.execute)
        graph.add_node("react", self._react_step.execute)
        graph.add_node("act", self._act_node)
        graph.add_node("reflect", self._reflect_step.execute)
        graph.add_node("respond", self._respond_node)
        graph.add_edge(START, "retrieve_memory")
        graph.add_edge("retrieve_memory", "react")
        graph.add_conditional_edges(
            "react",
            self._react_step.route_after_decision,
            {"act": "act", "respond": "respond", "end": END},
        )
        graph.add_edge("act", "reflect")
        graph.add_edge("reflect", "react")
        graph.add_edge("respond", END)
        return graph.compile()

    def _act_node(self, state: ReActState) -> ReActState:
        return self._tool_step.execute(state)

    def _respond_node(self, state: ReActState) -> ReActState:
        return self._response_step.execute(state)


__all__ = ["ReActAgent"]
