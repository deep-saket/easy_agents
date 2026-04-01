"""Created: 2026-04-01

Purpose: Implements the DuckDB-backed warm memory layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.memory.backends.duckdb_backend import DuckDBMemoryBackend
from src.memory.base import BaseMemoryLayer
from src.memory.models import MemoryRecord


@dataclass(slots=True)
class WarmMemoryLayer(BaseMemoryLayer):
    """Stores primary long-term memory records in DuckDB."""

    db_path: Path
    schema_config_path: Path = Path("config/memory_tables.yaml")

    def __post_init__(self) -> None:
        self._backend = DuckDBMemoryBackend(self.db_path, self.schema_config_path)

    def add(self, item: MemoryRecord) -> MemoryRecord:
        return self._backend.add_record(item.model_copy(update={"layer": "warm"}))

    def get(self, memory_id: str) -> MemoryRecord | None:
        return self._backend.get_record(memory_id)

    def search(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryRecord]:
        return self._backend.query_records(query=query, filters=filters, limit=limit)

    def list_older_than(self, cutoff_iso: str, *, scope: str | None = None, limit: int = 500) -> list[MemoryRecord]:
        return self._backend.archive_records(scope=scope, older_than_iso=cutoff_iso, limit=limit)

    def delete(self, memory_id: str) -> None:
        self._backend.delete_record(memory_id)
