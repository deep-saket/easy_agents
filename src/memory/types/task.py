"""Created: 2026-03-31

Purpose: Implements the task module for the shared memory platform layer.

Task memory

deferred work, follow-ups, sleeping jobs, background compaction tasks
warm active queue, cold after completion/archive
"""

from __future__ import annotations

from typing import Literal

from src.memory.models import MemoryItem


class TaskMemory(MemoryItem):
    type: Literal["task"] = "task"
