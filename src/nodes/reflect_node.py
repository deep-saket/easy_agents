"""Created: 2026-03-31

Purpose: Implements the reusable reflection node for shared agent graphs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.nodes.base import BaseGraphNode
from src.nodes.types import AgentState, NodeUpdate
from src.memory.base import BaseMemoryStore
from src.memory.types import ReflectionMemory, ReflectionMemoryContent


@dataclass(slots=True)
class ReflectNode(BaseGraphNode):
    """Writes lightweight reflection memory after a tool observation.

    The shared graph uses this node to capture a compact post-action trace that
    can later help retrieval, debugging, and future reflection workflows. The
    node is intentionally conservative: if no long-term memory store is
    configured, it becomes a no-op and does not affect agent behavior.
    """

    memory_store: BaseMemoryStore | None = None
    agent_name: str = "platform"
    llm: Any | None = None

    def execute(self, state: AgentState) -> NodeUpdate:
        """Stores a reflection item derived from the latest tool observation.

        Args:
            state: The current shared graph state.

        Returns:
            An empty state update. Reflection is a side effect only.
        """
        self._record_llm_usage(state, node_name="reflect")
        if self.memory_store is None:
            return {}
        observation = state.get("observation")
        if not observation:
            return {}
        decision = state.get("decision")
        tool_name = observation.get("tool_name", "unknown")
        output = observation.get("output")
        content = ReflectionMemoryContent(
            reasoning=getattr(decision, "thought", None),
            summary=f"Observed output from tool `{tool_name}`.",
            improvement_suggestions=[],
            failure_analysis=None,
        )
        self.memory_store.add(
            ReflectionMemory(
                layer="warm",
                content=content.model_dump(mode="json"),
                metadata={
                    "agent": self.agent_name,
                    "tags": ["reflection", tool_name],
                    "source": "reflect_node",
                    "priority": "low",
                    "tool_name": tool_name,
                    "llm_name": self._llm_name(),
                    "observation_preview": self._preview_output(output),
                },
            )
        )
        return {}

    @staticmethod
    def _preview_output(output: Any) -> str:
        """Builds a short serializable preview of a tool output payload.

        Args:
            output: Arbitrary tool output.

        Returns:
            A short string representation truncated to a safe length.
        """
        preview = str(output)
        return preview[:280]
