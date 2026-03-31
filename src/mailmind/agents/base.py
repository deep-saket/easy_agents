from __future__ import annotations

from abc import ABC, abstractmethod

from mailmind.memory.conversation import ConversationMemory
from mailmind.schemas.tools import PlannerDecision


class BasePlanner(ABC):
    @abstractmethod
    def plan(
        self,
        *,
        user_input: str,
        memory: ConversationMemory,
        observation: dict | None = None,
    ) -> PlannerDecision:
        raise NotImplementedError
