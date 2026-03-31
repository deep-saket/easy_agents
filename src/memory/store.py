"""Created: 2026-03-31

Purpose: Implements the store module for the shared memory platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from memory.base import BaseMemoryStore
from memory.indexer import MemoryIndexer
from memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from memory.models import MemoryItem, utc_now


@dataclass(slots=True)
class MemoryStore(BaseMemoryStore):
    """Coordinates hot, warm, and cold memory layers.

    The store is the main write entrypoint for long-term memory. It decides
    where new memories should live, rehydrates archived memories when accessed,
    and periodically archives stale warm memories into cold storage.
    """

    hot_layer: HotMemoryLayer
    warm_layer: WarmMemoryLayer
    cold_layer: ColdMemoryLayer
    indexer: MemoryIndexer
    archive_after_days: int = 30

    def add(self, item: MemoryItem) -> MemoryItem:
        """Stores a memory item in the appropriate layer.

        Cold memories are appended directly to the archive. All other memories
        are normalized into warm storage, and hot memories are additionally
        cached in the hot layer.

        Args:
            item: The memory item to store.

        Returns:
            The stored memory item.
        """
        if item.layer == "cold":
            return self.cold_layer.add(item)
        stored = self.indexer.index(item.model_copy(update={"layer": "warm"}))
        if item.layer == "hot":
            self.hot_layer.add(stored)
        return stored

    def bulk_add(self, items: list[MemoryItem]) -> list[MemoryItem]:
        """Stores multiple memory items.

        Args:
            items: Memory items to store.

        Returns:
            The stored memory items.
        """
        return [self.add(item) for item in items]

    def get(self, memory_id: str) -> MemoryItem | None:
        """Retrieves a memory item and promotes it when necessary.

        Lookup order is hot, warm, then cold. A cold hit is rehydrated into
        warm storage and cached in hot storage.

        Args:
            memory_id: The unique memory identifier.

        Returns:
            The matching memory item when found, otherwise `None`.
        """
        hot_item = self.hot_layer.get(memory_id)
        if hot_item is not None:
            return hot_item
        warm_item = self.warm_layer.get(memory_id)
        if warm_item is not None:
            self.hot_layer.add(warm_item)
            return warm_item
        cold_item = self.cold_layer.get(memory_id)
        if cold_item is not None:
            promoted = self.indexer.index(cold_item.model_copy(update={"layer": "warm"}))
            self.hot_layer.add(promoted)
            return promoted
        return None

    def search(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryItem]:
        """Searches the primary warm memory layer.

        Retrieval orchestration across layers lives in `MemoryRetriever`. The
        store keeps this method as the canonical direct search API.

        Args:
            query: Free-text search input.
            filters: Optional structured filters.
            limit: Maximum number of results to return.

        Returns:
            Matching memory items from warm storage.
        """
        return self.warm_layer.search(query=query, filters=filters, limit=limit)

    def archive_old(self) -> int:
        """Moves stale warm memories into cold storage.

        Returns:
            The number of archived memories.
        """
        cutoff = utc_now() - timedelta(days=self.archive_after_days)
        candidates = self.warm_layer.list_older_than(cutoff.isoformat())
        archived = 0
        for item in candidates:
            self.cold_layer.add(item.model_copy(update={"layer": "cold"}))
            self.warm_layer.delete(item.id)
            archived += 1
        return archived
