"""Planner for collection memory helper agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from src.nodes.planner_node import PlannerNode


@dataclass(slots=True)
class CollectionMemoryHelperPlanner(PlannerNode):
    """Plans memory update extraction and persistence."""

    def plan(
        self,
        *,
        user_input: str,
        memory: Any | None = None,
        observation: dict[str, Any] | None = None,
        memory_context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        available_tools: list[Any] | None = None,
    ) -> Any:
        del memory, memory_context, system_prompt, user_prompt, available_tools
        if observation:
            output = observation.get("output") if isinstance(observation, dict) else {}
            return SimpleNamespace(
                thought="Memory update complete.",
                tool_call=None,
                respond_directly=True,
                response_text=f"Memory helper updated stores. Extracted events: {output.get('extracted_key_events', [])}",
                done=True,
            )

        payload = self._parse_payload(user_input)
        return SimpleNamespace(
            thought="Updating global and user key-event memory stores.",
            tool_call=SimpleNamespace(tool_name="update_key_event_memory", arguments=payload),
            respond_directly=False,
            response_text=None,
            done=False,
        )

    @staticmethod
    def _parse_payload(user_input: str) -> dict[str, Any]:
        try:
            payload = json.loads(user_input)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
        return {
            "session_id": "unknown",
            "trigger": {"reason": "unparsed_payload"},
            "conversation_messages": [{"role": "user", "content": user_input}],
            "conversation_state": {},
        }
