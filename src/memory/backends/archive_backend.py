"""Created: 2026-04-01

Purpose: Implements the long-term archive backend for cold memory storage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.memory.backends.base import MemoryBackend
from src.memory.layers.shared import filters_match
from src.memory.models import MemoryRecord
from src.memory.types import parse_memory_item


@dataclass(slots=True)
class ArchiveMemoryBackend(MemoryBackend):
    """Stores archived memory records in a local JSONL file."""

    file_path: Path

    def __post_init__(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.touch(exist_ok=True)

    def add_record(self, record: MemoryRecord) -> MemoryRecord:
        archived = record.model_copy(update={"layer": "cold"})
        with self.file_path.open("a", encoding="utf-8") as handle:
            handle.write(archived.model_dump_json() + "\n")
        return archived

    def get_record(self, record_id: str) -> MemoryRecord | None:
        for record in self._read_all():
            if record.id == record_id:
                return record
        return None

    def query_records(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryRecord]:
        filters = filters or {}
        query_text = query.lower().strip()
        matches: list[MemoryRecord] = []
        for record in self._read_all():
            if query_text and query_text not in (record.content_text or "").lower():
                continue
            if not filters_match(record, filters):
                continue
            matches.append(record)
        return matches[:limit]

    def archive_records(self, *, scope: str | None = None, older_than_iso: str | None = None, limit: int = 500) -> list[MemoryRecord]:
        records = self._read_all()
        matches: list[MemoryRecord] = []
        for record in records:
            if scope is not None and record.scope != scope:
                continue
            if older_than_iso is not None and record.created_at.isoformat() >= older_than_iso:
                continue
            matches.append(record)
        return matches[:limit]

    def delete_record(self, record_id: str) -> None:
        records = [record for record in self._read_all() if record.id != record_id]
        with self.file_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(record.model_dump_json() + "\n")

    def _read_all(self) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        for line in self.file_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(parse_memory_item(json.loads(line)))
        return records
