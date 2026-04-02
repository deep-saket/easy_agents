"""Created: 2026-03-30

Purpose: Implements the base module for the shared mailmind platform layer.
"""

from __future__ import annotations

from src.planner.base import BasePlanner as SharedBasePlanner
from src.mailmind.memory.conversation import ConversationMemory
from src.mailmind.schemas.tools import PlannerDecision


class BasePlanner(SharedBasePlanner):
    """Defines the shared planning contract used by agents."""
    def plan(
        self,
        *,
        user_input: str,
        memory: ConversationMemory | None = None,
        observation: dict | None = None,
        memory_context: dict[str, object] | None = None,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        available_tools: list[object] | None = None,
    ) -> PlannerDecision:
        del user_input, memory, observation, memory_context, system_prompt, user_prompt, available_tools
        raise NotImplementedError
