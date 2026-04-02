"""Created: 2026-03-31

Purpose: Implements the base module for the shared memory platform layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.memory.models import MemoryRecord


class BaseMemoryLayer(ABC):
    """Defines the contract for one physical long-term memory layer.

    A memory layer is the lowest-level storage abstraction in the memory
    subsystem. Each concrete layer owns one storage medium and one access
    pattern:

    - `HotMemoryLayer` keeps a bounded in-process cache for very recent items.
    - `WarmMemoryLayer` keeps the primary searchable store in DuckDB.
    - `ColdMemoryLayer` keeps archived memories in JSONL for cheap retention.

    The important point is that a layer does not decide *which* memories should
    be written or *when* data should move between layers. It only knows how to
    store, fetch, and search memory items within its own medium. That routing
    logic belongs to `BaseMemoryStore` and its concrete implementation
    `MemoryStore`.
    """

    @abstractmethod
    def add(self, item: MemoryRecord) -> MemoryRecord:
        """Stores a memory item inside this layer only.

        Args:
            item: The memory object to persist in this physical layer.

        Returns:
            The stored memory item, potentially normalized for the layer. For
            example, a warm layer may force `layer="warm"` before persisting.
        """
        raise NotImplementedError

    @abstractmethod
    def get(self, memory_id: str) -> MemoryRecord | None:
        """Fetches a memory item by identifier from this layer only.

        Args:
            memory_id: The unique memory identifier.

        Returns:
            The matching memory item when found, otherwise `None`.
        """
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryRecord]:
        """Searches this layer for memory items matching the query and filters.

        Args:
            query: Free-text search input to evaluate inside this layer.
            filters: Optional structured filters such as memory type, agent, or
                metadata constraints.
            limit: Maximum number of results to return.

        Returns:
            Matching memory items ordered according to the layer's retrieval
            strategy.
        """
        raise NotImplementedError


class BaseMemoryStore(ABC):
    """Defines the contract for the orchestrating long-term memory system.

    The store sits *above* individual layers and provides the API the rest of
    the platform should use for long-term memory operations. Unlike a layer, a
    store is responsible for system-wide policy decisions such as:

    - routing a write to hot, warm, or cold storage
    - promoting a cold memory back into warm storage when it becomes relevant
    - archiving stale warm memories into cold storage
    - exposing a single interface that hides the underlying storage topology

    In this project, `MemoryStore` is the concrete implementation of this
    abstraction. Agent code and tools should depend on the store abstraction
    rather than hard-coding a specific layer.
    """

    @abstractmethod
    def add(self, item: MemoryRecord) -> MemoryRecord:
        """Writes a single memory item into the managed long-term memory system.

        Args:
            item: The memory object to store.

        Returns:
            The stored memory item after routing and normalization. The concrete
            store may change the target layer as part of its policy.
        """
        raise NotImplementedError

    @abstractmethod
    def bulk_add(self, items: list[MemoryRecord]) -> list[MemoryRecord]:
        """Writes multiple memory items in one operation.

        Args:
            items: Memory objects to store.

        Returns:
            The stored memory items after routing.
        """
        raise NotImplementedError

    @abstractmethod
    def get(self, memory_id: str) -> MemoryRecord | None:
        """Fetches a memory item from the managed memory system.

        Args:
            memory_id: The unique memory identifier.

        Returns:
            The matching memory item when found, otherwise `None`. A concrete
            store may promote or cache the item during retrieval.
        """
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryRecord]:
        """Searches the managed memory system for relevant items.

        Args:
            query: Free-text search input.
            filters: Optional structured filters such as type, agent, or tags.
            limit: Maximum number of results to return.

        Returns:
            Matching memory items from the store's primary query path. The store
            may delegate to a retriever or a designated primary layer.
        """
        raise NotImplementedError

    @abstractmethod
    def archive_old(self) -> int:
        """Archives stale warm memories into cold storage.

        Returns:
            The number of memories archived during the run. This operation is a
            maintenance concern and should not normally happen inside the main
            agent reasoning loop.
        """
        raise NotImplementedError
