"""Created: 2026-04-01

Purpose: Implements layered retrieval across hot, warm, and cold memory.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.models import MemoryRecord
from src.memory.retrieval.ranking import score_memory
from src.memory.store import MemoryStore


@dataclass(slots=True)
class LayeredMemoryRetriever:
    """Retrieves memory records from local layered storage in ranked order."""

    store: MemoryStore

    def retrieve(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryRecord]:
        filters = filters or {}
        hot_results = self.store.hot_layer.search(query=query, filters=filters, limit=limit)
        warm_results = self.store.warm_layer.search(query=query, filters=filters, limit=limit)
        combined = self._dedupe(hot_results + warm_results)
        if len(combined) < limit:
            cold_results = self.store.cold_layer.search(query=query, filters=filters, limit=limit)
            combined = self._dedupe(combined + cold_results)
            for record in cold_results[: min(limit, 5)]:
                self.store.add(record.model_copy(update={"layer": "warm"}))
        return sorted(combined, key=lambda record: score_memory(record, query, filters), reverse=True)[:limit]

    @staticmethod
    def _dedupe(records: list[MemoryRecord]) -> list[MemoryRecord]:
        seen: dict[str, MemoryRecord] = {}
        for record in records:
            seen[record.id] = record
        return list(seen.values())
