"""Created: 2026-04-01

Purpose: Defines the shared base class for reusable graph nodes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.nodes.types import AgentState, NodeUpdate


class BaseGraphNode(ABC):
    """Defines the shared contract for all predefined LangGraph nodes.

    The platform is moving toward a node-first agent model where agents are
    composed from reusable graph nodes instead of inheriting a monolithic agent
    implementation. For that to remain easy to use, every predefined node
    should look the same from the outside:

    - it receives the same shared state object
    - it returns a partial state update
    - it may optionally expose routing logic for conditional graph edges

    This base class exists to make that contract explicit. A node should only
    implement one step of graph behavior. It should not own the full turn loop
    or agent lifecycle.
    """

    llm: Any | None = None

    @abstractmethod
    def execute(self, state: AgentState) -> NodeUpdate:
        """Runs one node step for the provided graph state.

        Args:
            state: The current agent graph state accumulated so far in the turn.

        Returns:
            A partial update that LangGraph merges back into the shared state.
            Nodes should return only the keys they are responsible for
            producing or changing.
        """
        raise NotImplementedError

    def _llm_name(self) -> str | None:
        """Returns a stable display name for the node's bound LLM.

        Returns:
            The configured model name when present, otherwise the LLM class
            name. Returns `None` when the node has no bound LLM.
        """
        if self.llm is None:
            return None
        model_name = getattr(self.llm, "model_name", None)
        if isinstance(model_name, str) and model_name:
            return model_name
        return type(self.llm).__name__

    def _record_llm_usage(self, state: AgentState, *, node_name: str) -> None:
        """Records which LLM-backed nodes participated in the current turn.

        Args:
            state: The current agent graph state.
            node_name: Stable node identifier such as `planner` or `response`.
        """
        llm_name = self._llm_name()
        if llm_name is None:
            return
        memory = state.get("memory")
        if memory is None:
            return
        node_llms = dict(getattr(memory, "state", {}).get("node_llms", {}))
        node_llms[node_name] = llm_name
        memory.set_state(node_llms=node_llms)

    def route(self, state: AgentState) -> str:
        """Returns the next edge label for nodes that support routing.

        Args:
            state: The current agent graph state after this node has executed.

        Returns:
            A route label understood by the graph definition.

        Raises:
            NotImplementedError: If the node does not support conditional
                routing.
        """
        raise NotImplementedError(f"{type(self).__name__} does not define routing.")
