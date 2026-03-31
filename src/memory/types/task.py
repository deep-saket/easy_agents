"""Created: 2026-03-31

Purpose: Implements the task module for the shared memory platform layer.
"""

from __future__ import annotations

from typing import Literal

from memory.models import MemoryItem


class TaskMemory(MemoryItem):
    type: Literal["task"] = "task"
