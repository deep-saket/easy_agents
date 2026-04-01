"""Created: 2026-03-31

Purpose: Implements the episodic module for the shared memory platform layer.

Episodic memory

events and experiences
emails received, user queries, tool executions, decisions taken
hot briefly, then warm, then cold
"""

from __future__ import annotations

from typing import Literal

from src.memory.models import MemoryItem


class EpisodicMemory(MemoryItem):
    type: Literal["episodic"] = "episodic"
