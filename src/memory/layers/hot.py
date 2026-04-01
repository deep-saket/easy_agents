"""Created: 2026-04-01

Purpose: Implements the hot memory layer using an in-process cache.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.memory.base import BaseMemoryLayer
from src.memory.hot.cache import HotMemoryCache
from src.memory.models import MemoryRecord


@dataclass(slots=True)
class HotMemoryLayer(BaseMemoryLayer):
    """Wraps the in-process hot memory cache behind the layer interface."""

    max_items: int = 256
    _cache: HotMemoryCache = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._cache = HotMemoryCache(max_items=self.max_items)

    def add(self, item: MemoryRecord) -> MemoryRecord:
        return self._cache.add(item)

    def get(self, memory_id: str) -> MemoryRecord | None:
        return self._cache.get(memory_id)

    def search(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryRecord]:
        return self._cache.search(query=query, filters=filters, limit=limit)
