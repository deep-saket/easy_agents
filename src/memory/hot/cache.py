"""Created: 2026-04-01

Purpose: Implements the in-memory hot cache for recent memory records.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field

from src.memory.layers.shared import filters_match
from src.memory.models import MemoryRecord


@dataclass(slots=True)
class HotMemoryCache:
    """Caches the most recent memory records in process memory."""

    max_items: int = 256
    _items: OrderedDict[str, MemoryRecord] = field(default_factory=OrderedDict, init=False, repr=False)

    def add(self, record: MemoryRecord) -> MemoryRecord:
        self._items[record.id] = record.model_copy(update={"layer": "hot"})
        self._items.move_to_end(record.id)
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)
        return self._items[record.id]

    def get(self, record_id: str) -> MemoryRecord | None:
        record = self._items.get(record_id)
        if record is not None:
            self._items.move_to_end(record_id)
        return record

    def search(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryRecord]:
        query_text = query.lower().strip()
        matches: list[MemoryRecord] = []
        for record in reversed(self._items.values()):
            if query_text and query_text not in (record.content_text or "").lower():
                continue
            if filters and not filters_match(record, filters):
                continue
            matches.append(record)
            if len(matches) >= limit:
                break
        return matches
