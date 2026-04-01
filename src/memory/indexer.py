"""Created: 2026-04-01

Purpose: Implements indexing helpers for DuckDB-backed warm memory.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.layers import WarmMemoryLayer
from src.memory.models import MemoryRecord


@dataclass(slots=True)
class MemoryIndexer:
    """Indexes records into the primary warm memory layer.

    DuckDB is the primary structured store. The indexer remains as a small
    abstraction so vector indexing or secondary materialized indexes can be
    added later without changing the store API.
    """

    warm_layer: WarmMemoryLayer
    embeddings_enabled: bool = False

    def index(self, item: MemoryRecord) -> MemoryRecord:
        return self.warm_layer.add(item)

    def index_embedding_stub(self, item: MemoryRecord) -> None:
        del item
        return None
