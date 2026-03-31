"""Created: 2026-03-31

Purpose: Implements the memory search module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from memory.retriever import MemoryRetriever
from mailmind.schemas.tools import MemorySearchInput, MemorySearchOutput
from tools.base import BaseTool


@dataclass(slots=True)
class MemorySearchTool(BaseTool[MemorySearchInput, MemorySearchOutput]):
    """Exposes long-term memory retrieval through the shared tool interface."""

    retriever: MemoryRetriever
    name: str = "memory_search"
    description: str = "Search layered long-term memory across hot, warm, and cold storage."
    input_schema = MemorySearchInput
    output_schema = MemorySearchOutput

    def execute(self, input: MemorySearchInput) -> MemorySearchOutput:
        """Searches memory and returns structured results.

        Args:
            input: Query text, optional filters, and a result limit.

        Returns:
            Structured memory search results.
        """
        memories = self.retriever.retrieve(query=input.query, filters=input.filters, limit=input.limit)
        return MemorySearchOutput(total=len(memories), memories=memories)
