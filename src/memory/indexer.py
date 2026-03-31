"""Created: 2026-03-31

Purpose: Implements the indexer module for the shared memory platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from memory.layers import WarmMemoryLayer
from memory.models import MemoryItem


@dataclass(slots=True)
class MemoryIndexer:
    """Indexes memories into the primary warm storage layer.

    The current implementation uses SQLite FTS through `WarmMemoryLayer`.
    Embedding support is intentionally stubbed so the platform can add vector
    search later without changing the store interface.
    """

    warm_layer: WarmMemoryLayer
    embeddings_enabled: bool = False

    def index(self, item: MemoryItem) -> MemoryItem:
        """Indexes a memory item into warm storage.

        Args:
            item: The memory item to index.

        Returns:
            The indexed memory item.
        """
        return self.warm_layer.add(item)

    def index_embedding_stub(self, item: MemoryItem) -> None:
        """Placeholder for future vector indexing support.

        Args:
            item: The memory item that would be embedded in a future version.
        """
        if not self.embeddings_enabled:
            return
        # TODO: Add vector indexing when a shared embedding service is introduced.
        _ = item
