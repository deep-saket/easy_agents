"""Created: 2026-03-31

Purpose: Implements the sleeping module for the shared memory platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from memory.models import SleepingTask


@dataclass(slots=True)
class SleepingMemoryQueue:
    file_path: Path

    def __post_init__(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.touch(exist_ok=True)

    def enqueue(self, task: SleepingTask) -> SleepingTask:
        with self.file_path.open("a", encoding="utf-8") as handle:
            handle.write(task.model_dump_json() + "\n")
        return task

    def list_tasks(self) -> list[SleepingTask]:
        tasks: list[SleepingTask] = []
        for line in self.file_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            tasks.append(SleepingTask.model_validate_json(stripped))
        return sorted(tasks, key=lambda task: (-task.priority, task.created_at))

    def pop_next(self) -> SleepingTask | None:
        tasks = self.list_tasks()
        if not tasks:
            return None
        next_task = tasks[0]
        remaining = tasks[1:]
        with self.file_path.open("w", encoding="utf-8") as handle:
            for task in remaining:
                handle.write(task.model_dump_json() + "\n")
        return next_task
