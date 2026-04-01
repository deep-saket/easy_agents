"""Created: 2026-03-30

Purpose: Implements the base module for the shared mailmind platform layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.mailmind.memory.conversation import ConversationMemory
from src.mailmind.schemas.tools import PlannerDecision


class BasePlanner(ABC):
    @abstractmethod
    def plan(
        self,
        *,
        user_input: str,
        memory: ConversationMemory,
        observation: dict | None = None,
        memory_context: dict[str, object] | None = None,
    ) -> PlannerDecision:
        raise NotImplementedError
