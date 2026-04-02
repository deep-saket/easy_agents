"""Created: 2026-03-31

Purpose: Implements the task module for the shared memory platform layer.

Task memory

deferred work, follow-ups, sleeping jobs, background compaction tasks
warm active queue, cold after completion/archive
"""

from __future__ import annotations

from typing import Literal

from src.memory.types.base import TypedMemoryRecord


class TaskMemory(TypedMemoryRecord):
    """Represents task memory."""
    type: Literal["task"] = "task"
    layer: Literal["warm", "cold"] = "warm"
    scope: Literal["agent_local", "global"] = "agent_local"
    default_layer = "warm"
    default_scope = "agent_local"
