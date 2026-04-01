"""Created: 2026-04-01

Purpose: Exposes the sleeping task queue through the legacy import.
"""

from src.memory.tasks.sleeping_queue import SleepingTaskQueue as SleepingMemoryQueue

__all__ = ["SleepingMemoryQueue"]
