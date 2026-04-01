"""Created: 2026-03-31

Purpose: Implements the reusable tool execution node for shared agent graphs.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.agents.nodes.types import ReActState
from src.tools.executor import ToolExecutor


@dataclass(slots=True)
class ToolExecutionNode:
    """Executes a selected tool call and returns a normalized observation."""

    executor: ToolExecutor

    def execute(self, state: ReActState) -> ReActState:
        """Runs the selected tool call from the planner decision.

        Args:
            state: The current shared graph state.

        Returns:
            A partial state update containing the normalized observation.
        """
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


ToolNode = ToolExecutionNode
