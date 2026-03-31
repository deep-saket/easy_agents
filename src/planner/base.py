from __future__ import annotations

from abc import ABC, abstractmethod


class BasePlanner(ABC):
    @abstractmethod
    def plan(self, user_input: str, memory, available_tools, observation=None):
        raise NotImplementedError

