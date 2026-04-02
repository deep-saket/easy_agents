"""Created: 2026-03-31

Purpose: Implements the reusable router node for multi-agent graph workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from src.agents.nodes.base import BaseGraphNode
from src.agents.nodes.types import AgentState, NodeUpdate


class RouterProtocol(Protocol):
    """Describes the minimal router interface used by the node."""

    def route(self, *, user_input: str, state: AgentState) -> str:
        """Returns the selected route or agent key for the current turn."""
        ...


@dataclass(slots=True)
class RouterNode(BaseGraphNode):
    """Selects the next route or agent for a multi-agent workflow.

    This node is not MailMind-specific. It exists so an orchestrator agent can
    reuse the same graph vocabulary later without changing the core platform.
    """

    router: RouterProtocol | None = None
    llm: Any | None = None

    def execute(self, state: AgentState) -> NodeUpdate:
        """Computes a route decision for the current graph state.

        Args:
            state: The current shared graph state.

        Returns:
            A partial state update containing the selected route when a router
            is configured, otherwise an empty update.
        """
        self._record_llm_usage(state, node_name="router")
        if self.router is None:
            return {}
        route = self.router.route(user_input=state["user_input"], state=state)
        return {"route": route}
