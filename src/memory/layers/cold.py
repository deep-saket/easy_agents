"""Created: 2026-03-31

Purpose: Implements the cold module for the shared memory platform layer.
"""

from __future__ import annotations

import json
from pathlib import Path

from memory.base import BaseMemoryLayer
from memory.layers.shared import content_to_text, filters_match
from memory.models import MemoryItem
from memory.types import parse_memory_item


class ColdMemoryLayer(BaseMemoryLayer):
    """Archives long-term memories as JSONL on disk.

    Cold memory is the cheapest, slowest layer. It is intended for older data
    that should remain accessible but does not need to stay in SQLite.
    """

    def __init__(self, file_path: Path) -> None:
        """Initializes the cold archive file.

        Args:
            file_path: JSONL path used for archived memories.
        """
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.touch(exist_ok=True)

    def add(self, item: MemoryItem) -> MemoryItem:
        """Appends a memory item to the cold JSONL archive."""
        stored = item.model_copy(update={"layer": "cold"})
        with self.file_path.open("a", encoding="utf-8") as handle:
            handle.write(stored.model_dump_json() + "\n")
        return stored

    def get(self, memory_id: str) -> MemoryItem | None:
        """Fetches an archived memory by identifier."""
        for item in reversed(self._read_all()):
            if item.id == memory_id:
                return item
        return None

    def search(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryItem]:
        """Searches archived memories using linear scan and metadata filters."""
        lowered = query.lower().strip()
        results: list[MemoryItem] = []
        for item in reversed(self._read_all()):
            if not filters_match(item, filters):
                continue
            haystack = f"{content_to_text(item.content)} {json.dumps(item.metadata, sort_keys=True)}".lower()
            if lowered and lowered not in haystack:
                continue
            results.append(item)
            if len(results) >= limit:
                break
        return results

    def _read_all(self) -> list[MemoryItem]:
        """Reads the entire cold archive into typed memory objects."""
        items: list[MemoryItem] = []
        for line in self.file_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            items.append(parse_memory_item(stripped))
        return items
