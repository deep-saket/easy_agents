"""Created: 2026-03-31

Purpose: Implements the retriever module for the shared memory platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from memory.models import MemoryItem
from memory.store import MemoryStore


def _parse_created_at(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class MemoryRetriever:
    """Retrieves and ranks memories across multiple layers.

    The retriever implements the read policy described in the memory design:
    search hot first, use warm as the primary long-term layer, then fall back to
    cold storage and rehydrate useful results.
    """

    store: MemoryStore

    def retrieve(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryItem]:
        """Retrieves relevant memory items for a query.

        Args:
            query: Free-text search input.
            filters: Optional structured filters such as memory type or tags.
            limit: Maximum number of results to return.

        Returns:
            Ranked memory items merged across available layers.
        """
        filters = filters or {}
        hot_results = self.store.hot_layer.search(query=query, filters=filters, limit=limit)
        warm_results = self.store.warm_layer.search(query=query, filters=filters, limit=limit)
        combined = self._dedupe(hot_results + warm_results)
        if len(combined) < limit:
            cold_results = self.store.cold_layer.search(query=query, filters=filters, limit=limit)
            combined = self._dedupe(combined + cold_results)
            for item in cold_results[: min(limit, 5)]:
                self.store.add(item.model_copy(update={"layer": "warm"}))
        ranked = sorted(combined, key=lambda item: self._score(item, query, filters), reverse=True)
        return ranked[:limit]

    @staticmethod
    def _dedupe(items: list[MemoryItem]) -> list[MemoryItem]:
        """Removes duplicate memories while preserving the most recent copy."""
        seen: dict[str, MemoryItem] = {}
        for item in items:
            seen[item.id] = item
        return list(seen.values())

    @staticmethod
    def _score(item: MemoryItem, query: str, filters: dict[str, object]) -> float:
        """Computes a simple ranking score for a memory item.

        The score combines keyword relevance, metadata matches, priority, layer
        bias, and recency.
        """
        score = 0.0
        content_text = str(item.content).lower()
        query_lower = query.lower().strip()
        if query_lower:
            score += content_text.count(query_lower) * 5
            if query_lower in str(item.metadata).lower():
                score += 2
        metadata_filters = filters.get("metadata", {})
        if isinstance(metadata_filters, dict):
            for key, value in metadata_filters.items():
                if item.metadata.get(key) == value:
                    score += 3
        priority = item.normalized_metadata().get("priority", "medium")
        if priority == "high":
            score += 6
        elif priority == "medium":
            score += 3
        elif priority == "low":
            score += 1
        age_seconds = max((datetime.now(timezone.utc) - _parse_created_at(item.created_at)).total_seconds(), 1.0)
        score += 1 / age_seconds * 10000
        if item.layer == "hot":
            score += 4
        elif item.layer == "warm":
            score += 2
        return score
