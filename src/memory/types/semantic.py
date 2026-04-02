"""Created: 2026-03-31

Purpose: Implements the semantic module for the shared memory platform layer.

Semantic memory

distilled facts
user preferences, important people, company priorities, stable learned patterns
warm primarily, optionally hot when active
"""

from __future__ import annotations

from typing import Literal

from src.memory.types.base import TypedMemoryRecord


class SemanticMemory(TypedMemoryRecord):
    """Represents semantic memory."""
    type: Literal["semantic"] = "semantic"
    layer: Literal["hot", "warm", "cold"] = "warm"
    scope: Literal["agent_local", "global"] = "agent_local"
    default_layer = "warm"
    default_scope = "agent_local"
