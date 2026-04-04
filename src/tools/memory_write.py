"""Created: 2026-03-31

Purpose: Implements the memory write module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.store import MemoryStore
from src.schemas.tool_io import MemoryWriteInput, MemoryWriteOutput
from src.tools.base import BaseTool


@dataclass(slots=True)
class MemoryWriteTool(BaseTool[MemoryWriteInput, MemoryWriteOutput]):
    """Exposes memory writes through the shared tool interface."""

    store: MemoryStore
    name: str = "memory_write"
    description: str = "Write a structured memory item into layered memory storage."
    input_schema = MemoryWriteInput
    output_schema = MemoryWriteOutput

    def execute(self, input: MemoryWriteInput) -> MemoryWriteOutput:
        """Stores a typed memory item.

        Args:
            input: The memory item to persist.

        Returns:
            The stored memory item wrapped in the tool output schema.
        """
        item = self.store.add(input.item)
        return MemoryWriteOutput(item=item)
