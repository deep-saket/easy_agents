"""Created: 2026-04-01

Purpose: Implements reflection compression helpers.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.types import ReflectionMemory, ReflectionMemoryContent


@dataclass(slots=True)
class ReflectionCompressor:
    """Compresses detailed episodic context into reflection summaries."""

    def compress(self, summary: str, *, agent_id: str | None = None, scope: str = "agent_local") -> ReflectionMemory:
        """Builds a reflection record from a concise summary string."""
        return ReflectionMemory(
            agent_id=agent_id,
            scope=scope,
            layer="warm",
            content=ReflectionMemoryContent(summary=summary),
        )
