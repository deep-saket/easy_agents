from __future__ import annotations

from abc import ABC, abstractmethod

from mailmind.schemas.tools import ToolPlan


class BasePlanner(ABC):
    @abstractmethod
    def plan(self, user_query: str) -> ToolPlan:
        raise NotImplementedError

