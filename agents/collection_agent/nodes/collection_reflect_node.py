"""Reflect node variant for collection demo loops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.nodes.reflect_node import ReflectNode


@dataclass(slots=True)
class CollectionReflectNode(ReflectNode):
    """Marks turn incomplete if payment or plan state needs more action."""

    def _reflect(self, *, user_input: str, observation: dict[str, Any] | None, decision: Any | None) -> dict[str, Any]:
        del user_input, decision
        if not observation:
            return {"reason": "No observation to validate.", "is_complete": True}
        tool_phase = observation.get("tool_phase") if isinstance(observation, dict) else None
        active = tool_phase if isinstance(tool_phase, dict) else observation
        output = active.get("output") if isinstance(active, dict) else None
        if isinstance(output, dict) and bool(output.get("needs_additional_action", False)):
            return {"reason": "Additional action required by tool output.", "is_complete": False}
        if isinstance(active, dict) and active.get("tool_name") == "pay_by_phone_collect":
            status = str((output or {}).get("status", ""))
            if status in {"failed", "partial"}:
                return {"reason": "Phone payment did not fully complete.", "is_complete": False}
        return {"reason": "Reflection complete.", "is_complete": True}

    def route(self, state: dict[str, Any]) -> str:
        if state.get("reflection_complete", self.default_is_complete):
            return self.complete_route
        routing_context = state.get("routing_context") if isinstance(state.get("routing_context"), dict) else {}
        plan_origin = str(routing_context.get("plan_origin", "react"))
        if plan_origin in {"pre_plan_intent", "post_memory_plan_intent"}:
            return "retry_plan_proposal"
        return "retry_react"
