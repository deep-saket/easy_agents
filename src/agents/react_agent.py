"""Created: 2026-03-31

Purpose: Implements the react agent module for the shared agents platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from memory.types import ProceduralMemory, WorkingMemory
from tools.executor import ToolExecutor


class PlannerProtocol(Protocol):
    def plan(
        self,
        *,
        user_input: str,
        memory: Any,
        observation: dict[str, Any] | None = None,
        memory_context: dict[str, Any] | None = None,
    ) -> Any:
        ...


class MemoryProtocol(Protocol):
    def add_user_message(self, content: str) -> None:
        ...

    def add_agent_message(self, content: str) -> None:
        ...

    def set_state(self, **kwargs: object) -> None:
        ...


class SessionStoreProtocol(Protocol):
    def load(self, session_id: str) -> MemoryProtocol:
        ...


class ReActState(TypedDict, total=False):
    user_input: str
    memory: MemoryProtocol
    memory_context: dict[str, Any]
    decision: Any
    observation: dict[str, Any] | None
    response: str
    steps: int


@dataclass(slots=True)
class ReActAgent:
    planner: PlannerProtocol
    executor: ToolExecutor
    session_store: SessionStoreProtocol
    memory_retriever: Any | None = None
    _graph: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._graph = self._build_graph()

    def run(self, user_input: str, session_id: str) -> str:
        memory = self.session_store.load(session_id)
        memory.add_user_message(user_input)
        memory_context = self._build_memory_context(user_input=user_input, session_id=session_id, memory=memory)
        state = self._graph.invoke(
            {
                "user_input": user_input,
                "memory": memory,
                "memory_context": memory_context,
                "observation": None,
                "steps": 0,
            }
        )
        response = state.get("response", "I’m not sure what to do next.")
        memory.add_agent_message(response)
        return response

    def _build_memory_context(self, *, user_input: str, session_id: str, memory: MemoryProtocol) -> dict[str, Any]:
        semantic_memories: list[Any] = []
        episodic_memories: list[Any] = []
        if self.memory_retriever is not None:
            semantic_memories = self.memory_retriever.retrieve(user_input, filters={"type": "semantic"}, limit=5)
            episodic_memories = self.memory_retriever.retrieve(user_input, filters={"type": "episodic"}, limit=5)
        working_memory = WorkingMemory(
            session_id=session_id,
            current_goal=user_input,
            state=dict(getattr(memory, "state", {})),
            recent_items=[
                {"role": message.role, "content": message.content}
                for message in getattr(memory, "history", [])[-6:]
            ],
        )
        procedural_memory = ProceduralMemory(
            tool_names=[tool.name for tool in self.executor.registry.list_tools()],
            planner_names=[type(self.planner).__name__],
            prompt_names=[],
        )
        return {
            "semantic": semantic_memories,
            "episodic": episodic_memories,
            "working": working_memory,
            "procedural": procedural_memory,
        }

    def _build_graph(self) -> Any:
        graph = StateGraph(ReActState)
        graph.add_node("reason", self._reason_node)
        graph.add_node("act", self._act_node)
        graph.add_node("respond", self._respond_node)
        graph.add_edge(START, "reason")
        graph.add_conditional_edges(
            "reason",
            self._route_after_reason,
            {"act": "act", "respond": "respond", "end": END},
        )
        graph.add_edge("act", "reason")
        graph.add_edge("respond", END)
        return graph.compile()

    def _reason_node(self, state: ReActState) -> ReActState:
        decision = self.planner.plan(
            user_input=state["user_input"],
            memory=state["memory"],
            observation=state.get("observation"),
            memory_context=state.get("memory_context"),
        )
        return {
            "decision": decision,
            "steps": state.get("steps", 0) + 1,
        }

    def _route_after_reason(self, state: ReActState) -> str:
        if state.get("steps", 0) > 4:
            state["response"] = "I reached the tool limit for this turn. Please narrow the request."
            return "respond"
        decision = state["decision"]
        if getattr(decision, "respond_directly", False) or getattr(decision, "done", False):
            return "respond"
        if getattr(decision, "tool_call", None) is None:
            state["response"] = "I need a bit more detail to continue."
            return "respond"
        return "act"

    def _act_node(self, state: ReActState) -> ReActState:
        decision = state["decision"]
        tool_call = getattr(decision, "tool_call", None)
        assert tool_call is not None
        tool_result = self.executor.execute(tool_call.tool_name, tool_call.arguments)
        state["memory"].set_state(last_tool_used=tool_result["tool_name"])
        return {
            "observation": {
                "tool_name": tool_result["tool_name"],
                "output": tool_result["output"],
            }
        }

    def _respond_node(self, state: ReActState) -> ReActState:
        decision = state["decision"]
        response = getattr(decision, "response_text", None) or state.get("response") or "Done."
        return {"response": response}


__all__ = ["ReActAgent"]
