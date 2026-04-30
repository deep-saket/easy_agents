"""Connections Agent custom nodes built on shared node primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.nodes.reflect_node import ReflectNode


@dataclass(slots=True)
class ConnectionsReflectNode(ReflectNode):
    """Uses deterministic reflection completeness checks for offline runs."""

    def _reflect(self, *, user_input: str, observation: dict[str, Any] | None, decision: Any | None) -> dict[str, Any]:
        del user_input, decision
        if not observation:
            return {"reason": "No tool observation; response can proceed.", "is_complete": True}
        output = observation.get("output") if isinstance(observation, dict) else None
        if isinstance(output, dict) and bool(output.get("needs_additional_action", False)):
            return {
                "reason": "Tool output indicates additional action is required.",
                "is_complete": False,
            }
        return {
            "reason": "Observation is complete enough for user response.",
            "is_complete": True,
        }
