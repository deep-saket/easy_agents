"""Created: 2026-04-11

Purpose: Implements a lightweight MailMind-specific context formatter node.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.nodes.base import BaseGraphNode
from src.nodes.types import AgentState, NodeUpdate


@dataclass(slots=True)
class MailMindContextFormatterNode(BaseGraphNode):
    """Builds a compact text block from observation and memory context for response use."""

    def execute(self, state: AgentState) -> NodeUpdate:
        observation = state.get("observation")
        memory_context = state.get("memory_context")
        parts: list[str] = []
        if observation:
            parts.append(f"Observation:\n{self._stringify(observation)}")
        if memory_context:
            parts.append(f"Memory Context:\n{self._stringify(memory_context)}")
        if not parts:
            return {}
        return {"response": "\n\n".join(parts)}

    @staticmethod
    def _stringify(value: Any) -> str:
        try:
            return json.dumps(value, default=str, ensure_ascii=True, indent=2)
        except TypeError:
            return str(value)


__all__ = ["MailMindContextFormatterNode"]
