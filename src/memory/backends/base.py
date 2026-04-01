"""Created: 2026-04-01

Purpose: Defines backend contracts for warm and archive memory storage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.memory.models import MemoryRecord


class MemoryBackend(ABC):
    """Defines the contract for persistent memory backends."""

    @abstractmethod
    def add_record(self, record: MemoryRecord) -> MemoryRecord:
        """Persists one memory record."""
        raise NotImplementedError

    @abstractmethod
    def get_record(self, record_id: str) -> MemoryRecord | None:
        """Fetches one memory record by identifier."""
        raise NotImplementedError

    @abstractmethod
    def query_records(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryRecord]:
        """Queries memory records using text and structured filters."""
        raise NotImplementedError

    @abstractmethod
    def archive_records(self, *, scope: str | None = None, older_than_iso: str | None = None, limit: int = 500) -> list[MemoryRecord]:
        """Returns records eligible for archival."""
        raise NotImplementedError

    @abstractmethod
    def delete_record(self, record_id: str) -> None:
        """Deletes one record from the backend."""
        raise NotImplementedError
