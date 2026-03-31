"""Created: 2026-03-31

Purpose: Implements the hot module for the shared memory platform layer.
"""

from __future__ import annotations

import json
from collections import OrderedDict

from memory.base import BaseMemoryLayer
from memory.layers.shared import content_to_text, filters_match
from memory.models import MemoryItem


class HotMemoryLayer(BaseMemoryLayer):
    """Caches recently used memories in process memory.

    This layer is optimized for the fastest possible lookup of recent memory
    items. It is intentionally bounded and ephemeral.
    """

    def __init__(self, max_items: int = 256) -> None:
        """Initializes the hot memory cache.

        Args:
            max_items: Maximum number of memories retained in the cache.
        """
        self.max_items = max_items
        self._items: OrderedDict[str, MemoryItem] = OrderedDict()

    def add(self, item: MemoryItem) -> MemoryItem:
        """Stores a memory item in the hot cache."""
        self._items.pop(item.id, None)
        self._items[item.id] = item.model_copy(update={"layer": "hot"})
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)
        return self._items[item.id]

    def get(self, memory_id: str) -> MemoryItem | None:
        """Looks up a memory item in the hot cache by identifier."""
        item = self._items.get(memory_id)
        if item is None:
            return None
        self._items.move_to_end(memory_id)
        return item

    def search(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryItem]:
        """Searches cached memories using substring matching and filters."""
        lowered = query.lower().strip()
        results: list[MemoryItem] = []
        for item in reversed(self._items.values()):
            if not filters_match(item, filters):
                continue
            haystack = f"{content_to_text(item.content)} {json.dumps(item.metadata, sort_keys=True)}".lower()
            if lowered and lowered not in haystack:
                continue
            results.append(item)
            if len(results) >= limit:
                break
        return results
