"""Created: 2026-04-10

Purpose: Defines memory-specific vector index contracts and adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.memory.index.models import IndexSearchHit, IndexableMemoryRecord
from src.retrieval.models import IndexedItem
from src.retrieval.vector_backend import VectorRetrievalBackend


class MemoryIndexBackend(ABC):
    """Defines the contract for vector indexing over memory records."""

    @abstractmethod
    def upsert(self, record: IndexableMemoryRecord, vector: list[float]) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, record_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        vector: list[float],
        filters: dict[str, object] | None = None,
        limit: int = 20,
    ) -> list[IndexSearchHit]:
        raise NotImplementedError

    @abstractmethod
    def rebuild(self, items: list[tuple[IndexableMemoryRecord, list[float]]]) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class VectorMemoryIndexBackend(MemoryIndexBackend):
    """Adapts a generic vector backend to the memory-specific index interface."""

    backend: VectorRetrievalBackend

    def upsert(self, record: IndexableMemoryRecord, vector: list[float]) -> None:
        self.backend.upsert(IndexedItem(item_id=record.record_id, vector=vector, text=record.text, metadata=record.metadata))

    def delete(self, record_id: str) -> None:
        self.backend.delete(record_id)

    def search(
        self,
        vector: list[float],
        filters: dict[str, object] | None = None,
        limit: int = 20,
    ) -> list[IndexSearchHit]:
        hits = self.backend.search(vector=vector, filters=filters, limit=limit)
        return [
            IndexSearchHit(record_id=hit.item_id, similarity=hit.score, text=hit.text, metadata=hit.metadata)
            for hit in hits
        ]

    def rebuild(self, items: list[tuple[IndexableMemoryRecord, list[float]]]) -> None:
        self.backend.rebuild(
            [
                IndexedItem(item_id=record.record_id, vector=vector, text=record.text, metadata=record.metadata)
                for record, vector in items
            ]
        )


__all__ = ["MemoryIndexBackend", "VectorMemoryIndexBackend"]
