"""Created: 2026-04-01

Purpose: Implements the scope-aware layered memory store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from src.memory.base import BaseMemoryStore
from src.memory.indexer import MemoryIndexer
from src.memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from src.memory.models import MemoryRecord, utc_now


@dataclass(slots=True)
class MemoryStore(BaseMemoryStore):
    """Coordinates hot, warm, and cold storage for one memory scope."""

    hot_layer: HotMemoryLayer
    warm_layer: WarmMemoryLayer
    cold_layer: ColdMemoryLayer
    indexer: MemoryIndexer
    archive_after_days: int = 30
    default_scope: str = "agent_local"
    agent_id: str | None = None

    def _normalize_record(self, item: MemoryRecord) -> MemoryRecord:
        metadata = item.normalized_metadata()
        agent_id = item.agent_id or self.agent_id or metadata.get("agent_id") or metadata.get("agent")
        return item.model_copy(
            update={
                "agent_id": agent_id,
                "scope": item.scope or self.default_scope,
                "metadata": metadata,
            }
        )

    def add(self, item: MemoryRecord) -> MemoryRecord:
        record = self._normalize_record(item)
        if record.layer == "cold":
            return self.cold_layer.add(record)
        stored = self.indexer.index(record.model_copy(update={"layer": "warm"}))
        if item.layer == "hot":
            self.hot_layer.add(stored)
        return stored

    def bulk_add(self, items: list[MemoryRecord]) -> list[MemoryRecord]:
        return [self.add(item) for item in items]

    def get(self, memory_id: str) -> MemoryRecord | None:
        hot_record = self.hot_layer.get(memory_id)
        if hot_record is not None:
            return hot_record
        warm_record = self.warm_layer.get(memory_id)
        if warm_record is not None and self._matches_scope(warm_record):
            self.hot_layer.add(warm_record)
            return warm_record
        cold_record = self.cold_layer.get(memory_id)
        if cold_record is not None and self._matches_scope(cold_record):
            promoted = self.indexer.index(cold_record.model_copy(update={"layer": "warm"}))
            self.hot_layer.add(promoted)
            return promoted
        return None

    def search(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryRecord]:
        scoped_filters = self._scoped_filters(filters)
        return self.warm_layer.search(query=query, filters=scoped_filters, limit=limit)

    def archive_old(self) -> int:
        cutoff = utc_now() - timedelta(days=self.archive_after_days)
        candidates = self.warm_layer.list_older_than(cutoff.isoformat(), scope=self.default_scope, limit=500)
        archived = 0
        for record in candidates:
            if not self._matches_scope(record):
                continue
            self.cold_layer.add(record.model_copy(update={"layer": "cold", "archived_at": utc_now()}))
            self.warm_layer.delete(record.id)
            archived += 1
        return archived

    def _scoped_filters(self, filters: dict[str, object] | None) -> dict[str, object]:
        scoped_filters = dict(filters or {})
        scoped_filters.setdefault("scope", self.default_scope)
        if self.agent_id is not None and self.default_scope == "agent_local":
            scoped_filters.setdefault("agent_id", self.agent_id)
        return scoped_filters

    def _matches_scope(self, record: MemoryRecord) -> bool:
        if record.scope != self.default_scope:
            return False
        if self.default_scope == "agent_local" and self.agent_id is not None:
            return record.agent_id == self.agent_id
        return True
