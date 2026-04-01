"""Created: 2026-04-01

Purpose: Implements the cold memory layer using an archive backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.memory.backends.archive_backend import ArchiveMemoryBackend
from src.memory.base import BaseMemoryLayer
from src.memory.models import MemoryRecord


@dataclass(slots=True)
class ColdMemoryLayer(BaseMemoryLayer):
    """Exposes the cold archive backend through the layer interface."""

    file_path: Path

    def __post_init__(self) -> None:
        self._backend = ArchiveMemoryBackend(self.file_path)

    def add(self, item: MemoryRecord) -> MemoryRecord:
        return self._backend.add_record(item)

    def get(self, memory_id: str) -> MemoryRecord | None:
        return self._backend.get_record(memory_id)

    def search(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryRecord]:
        return self._backend.query_records(query=query, filters=filters, limit=limit)
