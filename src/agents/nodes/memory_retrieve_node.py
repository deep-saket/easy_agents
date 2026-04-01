"""Created: 2026-03-31

Purpose: Implements the reusable memory retrieval node for shared agent graphs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.agents.nodes.types import ReActState
from src.memory.types import ProceduralMemory, WorkingMemory
from src.tools.registry import ToolRegistry


@dataclass(slots=True)
class MemoryRetrieveNode:
    """Builds the structured memory context for the current agent turn.

    This node gathers the four runtime memory inputs expected by the shared
    planner flow:

    - semantic memory retrieved from long-term memory
    - episodic memory retrieved from long-term memory
    - working memory derived from the active session state
    - procedural memory derived from the available tools and planner identity

    It is intentionally generic and does not embed MailMind-specific logic.
    """

    tool_registry: ToolRegistry
    planner: Any
    memory_retriever: Any | None = None

    def execute(self, state: ReActState) -> ReActState:
        """Builds and stores the memory context for the current turn.

        Args:
            state: The current shared graph state.

        Returns:
            A partial state update containing the assembled memory context.
        """
        user_input = state["user_input"]
        memory = state["memory"]
        session_id = getattr(memory, "session_id", "unknown")
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
            tool_names=[tool.name for tool in self.tool_registry.list_tools()],
            planner_names=[type(self.planner).__name__],
            prompt_names=[],
        )
        return {
            "memory_context": {
                "semantic": semantic_memories,
                "episodic": episodic_memories,
                "working": working_memory,
                "procedural": procedural_memory,
            }
        }
