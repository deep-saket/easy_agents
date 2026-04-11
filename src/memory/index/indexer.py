"""Created: 2026-04-10

Purpose: Implements memory-specific embedding and indexing orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.index.base import MemoryIndexBackend
from src.memory.index.models import IndexableMemoryRecord
from src.memory.models import MemoryRecord
from src.retrieval.vector_backend import EmbeddingProvider


def memory_record_to_indexable(record: MemoryRecord) -> IndexableMemoryRecord:
    """Converts a memory record into indexable text plus filter metadata."""

    text = record.content_text or ""
    metadata = {
        "scope": record.scope,
        "agent_id": record.agent_id,
        "type": record.type,
        "layer": record.layer,
        "tags": list(record.tags),
        "source_type": record.source_type,
        "source_id": record.source_id,
    }
    return IndexableMemoryRecord(record_id=record.id, text=text, metadata=metadata)


@dataclass(slots=True)
class MemoryIndexer:
    """Embeds memory records and writes them into a memory index backend."""

    embedding_provider: EmbeddingProvider
    index_backend: MemoryIndexBackend

    def index_record(self, record: MemoryRecord) -> IndexableMemoryRecord:
        indexable = memory_record_to_indexable(record)
        vector = self.embedding_provider.embed_text(indexable.text)
        self.index_backend.upsert(indexable, vector)
        return indexable

    def index_records(self, records: list[MemoryRecord]) -> list[IndexableMemoryRecord]:
        indexable_records = [memory_record_to_indexable(record) for record in records]
        vectors = self.embedding_provider.embed_texts([record.text for record in indexable_records])
        for indexable, vector in zip(indexable_records, vectors, strict=False):
            self.index_backend.upsert(indexable, vector)
        return indexable_records

    def delete_record(self, record_id: str) -> None:
        self.index_backend.delete(record_id)

    def rebuild(self, records: list[MemoryRecord]) -> list[IndexableMemoryRecord]:
        indexable_records = [memory_record_to_indexable(record) for record in records]
        vectors = self.embedding_provider.embed_texts([record.text for record in indexable_records])
        self.index_backend.rebuild(list(zip(indexable_records, vectors, strict=False)))
        return indexable_records


__all__ = ["MemoryIndexer", "memory_record_to_indexable"]
