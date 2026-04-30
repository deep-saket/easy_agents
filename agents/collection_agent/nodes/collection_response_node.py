"""Collection-specific response node with target routing."""

from __future__ import annotations

from dataclasses import dataclass

from src.nodes.response_node import ResponseNode
from src.nodes.types import AgentState, NodeUpdate


@dataclass(slots=True)
class CollectionResponseNode(ResponseNode):
    """Emits response text and a response target for next-hop routing."""

    default_target: str = "customer"

    def execute(self, state: AgentState) -> NodeUpdate:
        update = ResponseNode.execute(self, state)
        target = str(state.get("response_target", self.default_target)).strip().lower()
        if target not in {"customer", "self", "discount_planning_agent"}:
            target = self.default_target
        update["response_target"] = target
        return update

    def route(self, state: AgentState) -> str:
        target = str(state.get("response_target", self.default_target)).strip().lower()
        if target not in {"customer", "self", "discount_planning_agent"}:
            return self.default_target
        return target
