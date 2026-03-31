"""Created: 2026-03-31

Purpose: Implements the base agent module for the shared agents platform layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAgent(ABC):
    def __init__(self, llm, planner, tool_registry, memory, storage, logger, memory_store=None, memory_retriever=None) -> None:
        self.llm = llm
        self.planner = planner
        self.tool_registry = tool_registry
        self.memory = memory
        self.storage = storage
        self.logger = logger
        self.memory_store = memory_store
        self.memory_retriever = memory_retriever

    @abstractmethod
    def run(self, user_input: str, session_id: str | None = None):
        raise NotImplementedError
