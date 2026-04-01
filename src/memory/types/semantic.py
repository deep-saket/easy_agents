"""Created: 2026-03-31

Purpose: Implements the semantic module for the shared memory platform layer.

Semantic memory

distilled facts
user preferences, important people, company priorities, stable learned patterns
warm primarily, optionally hot when active
"""

from __future__ import annotations

from typing import Literal

from src.memory.models import MemoryItem


class SemanticMemory(MemoryItem):
    type: Literal["semantic"] = "semantic"
