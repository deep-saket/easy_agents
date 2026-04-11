"""Created: 2026-04-10

Purpose: Implements hybrid keyword plus vector retrieval for memory records.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.index.base import MemoryIndexBackend
from src.memory.models import MemoryRecord
from src.memory.retrieval.ranking import score_memory
from src.memory.store import MemoryStore
from src.retrieval.vector_backend import EmbeddingProvider


@dataclass(slots=True)
class HybridMemoryRetriever:
    """Retrieves memory using warm-store filters plus vector similarity ranking."""

    store: MemoryStore
    embedding_provider: EmbeddingProvider
    index_backend: MemoryIndexBackend
    vector_top_k: int = 20
    keyword_weight: float = 0.35
    similarity_weight: float = 0.45
    store_weight: float = 0.20

    def retrieve(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryRecord]:
        filters = filters or {}
        keyword_results = self.store.search(query=query, filters=filters, limit=max(limit, self.vector_top_k))
        vector_hits = []
        if query.strip():
            query_vector = self.embedding_provider.embed_text(query)
            vector_hits = self.index_backend.search(query_vector, filters=filters, limit=max(limit, self.vector_top_k))

        similarity_by_id = {hit.record_id: hit.similarity for hit in vector_hits}
        merged: dict[str, MemoryRecord] = {record.id: record for record in keyword_results}
        keyword_ids = set(merged)
        for hit in vector_hits:
            if hit.record_id in merged:
                continue
            record = self.store.get(hit.record_id)
            if record is not None:
                merged[record.id] = record

        def hybrid_score(record: MemoryRecord) -> float:
            keyword_score = score_memory(record, query, filters)
            similarity = similarity_by_id.get(record.id, 0.0)
            store_bonus = 1.0 if record.id in keyword_ids else 0.0
            return (
                self.keyword_weight * keyword_score
                + self.similarity_weight * similarity
                + self.store_weight * store_bonus
            )

        return sorted(merged.values(), key=hybrid_score, reverse=True)[:limit]


__all__ = ["HybridMemoryRetriever"]
