"""Created: 2026-04-02

Purpose: Defines shared behavior for typed long-term memory records.
"""

from __future__ import annotations

from typing import Any, ClassVar, TypeVar

from src.memory.models import MemoryLayerName, MemoryRecord, MemoryScope

TypedMemoryRecordT = TypeVar("TypedMemoryRecordT", bound="TypedMemoryRecord")


class TypedMemoryRecord(MemoryRecord):
    """Adds type-owned storage and retrieval behavior to memory records.

    The goal of this base class is to keep memory-type behavior on the type
    itself rather than scattering it across policies, stores, and callers.
    Concrete types such as `SemanticMemory` and `EpisodicMemory` should define:

    - their default storage layer
    - their default scope
    - how callers should filter for them during retrieval

    This keeps the runtime model simple:

    - write memory as a typed object
    - store normalizes it through type-owned defaults
    - retrieve memory as the same typed object
    """

    default_layer: ClassVar[MemoryLayerName] = "warm"
    default_scope: ClassVar[MemoryScope] = "agent_local"

    def prepare_for_store(
        self,
        *,
        default_scope: str | None = None,
        agent_id: str | None = None,
    ) -> "TypedMemoryRecord":
        """Normalizes the record using type-owned defaults before storage.

        Args:
            default_scope: Optional store-level scope fallback.
            agent_id: Optional store-level agent identifier fallback.

        Returns:
            The normalized typed memory record ready for persistence.
        """
        metadata = self.normalized_metadata()
        resolved_scope = self.scope or default_scope or self.default_scope
        resolved_agent_id = self.agent_id or agent_id or metadata.get("agent_id") or metadata.get("agent")
        resolved_layer = self.layer or self.default_layer
        return self.model_copy(
            update={
                "agent_id": resolved_agent_id,
                "scope": resolved_scope,
                "layer": resolved_layer,
                "metadata": metadata,
            }
        )

    def store(
        self: TypedMemoryRecordT,
        store: Any,
        *,
        layer: MemoryLayerName | None = None,
        scope: str | None = None,
        agent_id: str | None = None,
    ) -> TypedMemoryRecordT:
        """Stores this typed memory through the provided memory store.

        Args:
            store: Memory store implementation, typically `MemoryStore`.
            layer: Optional target layer override.
            scope: Optional scope override.
            agent_id: Optional agent identifier override.

        Returns:
            The stored typed memory record.
        """
        record = self
        if layer is not None:
            record = record.model_copy(update={"layer": layer})
        if scope is not None:
            record = record.model_copy(update={"scope": scope})
        if agent_id is not None:
            record = record.model_copy(update={"agent_id": agent_id})
        stored = store.add(record)
        return self.__class__.model_validate(stored.model_dump(mode="json"))

    def store_hot(self: TypedMemoryRecordT, store: Any, **kwargs: object) -> TypedMemoryRecordT:
        """Stores this typed memory with a hot-layer preference."""
        return self.store(store, layer="hot", **kwargs)

    def store_warm(self: TypedMemoryRecordT, store: Any, **kwargs: object) -> TypedMemoryRecordT:
        """Stores this typed memory with a warm-layer preference."""
        return self.store(store, layer="warm", **kwargs)

    def store_cold(self: TypedMemoryRecordT, store: Any, **kwargs: object) -> TypedMemoryRecordT:
        """Stores this typed memory directly into the cold layer."""
        return self.store(store, layer="cold", **kwargs)

    @classmethod
    def retrieval_filters(cls, **filters: object) -> dict[str, object]:
        """Builds structured retrieval filters for this memory type.

        Args:
            **filters: Additional caller-supplied filters.

        Returns:
            Filters with the memory `type` pinned to the current subtype.
        """
        merged = dict(filters)
        merged["type"] = cls.model_fields["type"].default
        return merged

    @classmethod
    def get(cls: type[TypedMemoryRecordT], store: Any, memory_id: str) -> TypedMemoryRecordT | None:
        """Gets one typed memory by id from the store."""
        record = store.get(memory_id)
        if record is None or getattr(record, "type", None) != cls.model_fields["type"].default:
            return None
        return cls.model_validate(record.model_dump(mode="json"))

    @classmethod
    def search(
        cls: type[TypedMemoryRecordT],
        store: Any,
        query: str = "",
        *,
        limit: int = 20,
        **filters: object,
    ) -> list[TypedMemoryRecordT]:
        """Searches the memory store and returns only this concrete memory type."""
        records = store.search(query, filters=cls.retrieval_filters(**filters), limit=limit)
        return [cls.model_validate(record.model_dump(mode="json")) for record in records]

    @classmethod
    def retrieve(
        cls: type[TypedMemoryRecordT],
        retriever: Any,
        query: str = "",
        *,
        limit: int = 20,
        **filters: object,
    ) -> list[TypedMemoryRecordT]:
        """Retrieves this memory type through a layered retriever or router."""
        records = retriever.retrieve(query=query, filters=cls.retrieval_filters(**filters), limit=limit)
        return [cls.model_validate(record.model_dump(mode="json")) for record in records]

    @classmethod
    def archive(cls, store: Any, memory_id: str) -> TypedMemoryRecordT | None:
        """Moves a stored memory record to the cold layer and returns the typed result."""
        record = cls.get(store, memory_id)
        if record is None:
            return None
        archived = record.store_cold(store)
        if hasattr(store.warm_layer, "delete"):
            store.warm_layer.delete(memory_id)
        return archived
