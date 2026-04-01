"""Created: 2026-04-01

Purpose: Implements promotion helpers from reflection memory to semantic memory.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.types import ReflectionMemory, SemanticMemory


@dataclass(slots=True)
class ReflectionPromoter:
    """Promotes distilled reflections into reusable semantic knowledge."""

    def promote(self, reflection: ReflectionMemory, *, scope: str = "global") -> SemanticMemory:
        """Creates a semantic memory record from a reflection summary."""
        summary = reflection.content.summary if hasattr(reflection.content, "summary") else str(reflection.content)
        return SemanticMemory(
            agent_id=reflection.agent_id,
            scope=scope,
            layer="warm",
            content={"summary": summary, "source_reflection_id": reflection.id},
            metadata={"tags": ["promoted_reflection"]},
        )
