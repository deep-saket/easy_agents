"""Created: 2026-03-31

Purpose: Implements the episodic module for the shared memory platform layer.

Episodic memory

events and experiences
emails received, user queries, tool executions, decisions taken
hot briefly, then warm, then cold
"""

from __future__ import annotations

from typing import Literal

from src.memory.types.base import TypedMemoryRecord


class EpisodicMemory(TypedMemoryRecord):
    """Represents episodic memory."""
    type: Literal["episodic"] = "episodic"
    layer: Literal["hot", "warm", "cold"] = "hot"
    scope: Literal["agent_local"] = "agent_local"
    default_layer = "hot"
    default_scope = "agent_local"
