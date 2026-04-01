"""Created: 2026-03-31

Purpose: Implements the reusable react planning node for shared agent graphs.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.agents.nodes.types import PlannerProtocol, ReActState


@dataclass(slots=True)
class ReactNode:
    """Runs the planner and decides whether the graph should act or respond.

    This node is the shared equivalent of the "reason/select action" step in a
    ReAct loop. It does not execute tools directly. Instead, it records the
    planner decision and provides the routing logic that decides whether the
    next graph edge should go to tool execution or directly to response
    generation.
    """

    planner: PlannerProtocol
    max_steps: int = 4

    def execute(self, state: ReActState) -> ReActState:
        """Calls the planner for the current graph state.

        Args:
            state: The current shared graph state.

        Returns:
            A partial state update containing the planner decision and the
            incremented step count.
        """
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

    def route_after_decision(self, state: ReActState) -> str:
        """Chooses the next graph edge after planning.

        Args:
            state: The current shared graph state.

        Returns:
            The next node label: `act` when a tool should run, `respond` when a
            final textual reply should be generated, or `end` for termination.
        """
        if state.get("steps", 0) > self.max_steps:
            state["response"] = "I reached the tool limit for this turn. Please narrow the request."
            return "respond"
        decision = state["decision"]
        if getattr(decision, "respond_directly", False) or getattr(decision, "done", False):
            return "respond"
        if getattr(decision, "tool_call", None) is None:
            state["response"] = "I need a bit more detail to continue."
            return "respond"
        return "act"
