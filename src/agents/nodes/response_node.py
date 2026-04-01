"""Created: 2026-03-31

Purpose: Implements the reusable response node for shared agent graphs.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.agents.nodes.types import ReActState


@dataclass(slots=True)
class ResponseNode:
    """Builds the final user-facing response text for the current turn."""

    default_response: str = "Done."

    def execute(self, state: ReActState) -> ReActState:
        """Computes the final response text from the planner decision and state.

        Args:
            state: The current shared graph state.

        Returns:
            A partial state update containing the textual response.
        """
        decision = state["decision"]
        response = getattr(decision, "response_text", None) or state.get("response") or self.default_response
        return {"response": response}


RespondNode = ResponseNode
