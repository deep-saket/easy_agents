"""Created: 2026-03-31

Purpose: Implements the semantic module for the shared memory platform layer.
"""

from __future__ import annotations

from typing import Literal

from memory.models import MemoryItem


class SemanticMemory(MemoryItem):
    type: Literal["semantic"] = "semantic"
