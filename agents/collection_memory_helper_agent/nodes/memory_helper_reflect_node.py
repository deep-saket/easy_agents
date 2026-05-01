"""Reflect node for collection memory helper agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.nodes.reflect_node import ReflectNode


@dataclass(slots=True)
class CollectionMemoryHelperReflectNode(ReflectNode):
    """Ensures memory write output is complete before final response."""

    def _reflect(self, *, user_input: str, observation: dict[str, Any] | None, decision: Any | None) -> dict[str, Any]:
        del user_input, decision
        if not observation:
            return {"reason": "No observation from memory update tool.", "is_complete": False}
        output = observation.get("output") if isinstance(observation, dict) else {}
        if isinstance(output, dict) and output.get("status") == "updated":
            return {"reason": "Memory update succeeded.", "is_complete": True}
        return {"reason": "Memory update incomplete.", "is_complete": False}
