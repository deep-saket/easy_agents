from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAgent(ABC):
    def __init__(self, llm, planner, tool_registry, memory, storage, logger) -> None:
        self.llm = llm
        self.planner = planner
        self.tool_registry = tool_registry
        self.memory = memory
        self.storage = storage
        self.logger = logger

    @abstractmethod
    def run(self, user_input: str, session_id: str | None = None):
        raise NotImplementedError

