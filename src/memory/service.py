"""Created: 2026-04-01

Purpose: Provides a high-level memory service over local and global stores.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.models import MemoryRecord, RetrievalContext
from src.memory.router import MemoryRouter
from src.memory.store import MemoryStore


@dataclass(slots=True)
class MemoryService:
    """Coordinates local and global memory reads and writes for an agent."""

    local_store: MemoryStore
    global_store: MemoryStore
    router: MemoryRouter

    def add_local(self, record: MemoryRecord) -> MemoryRecord:
        """Writes a record to agent-local memory."""
        return self.local_store.add(record.model_copy(update={"scope": "agent_local"}))

    def add_global(self, record: MemoryRecord) -> MemoryRecord:
        """Writes a distilled record to global shared memory."""
        return self.global_store.add(record.model_copy(update={"scope": "global"}))

    def retrieve(
        self,
        query: str,
        filters: dict[str, object] | None = None,
        limit: int = 20,
        context: RetrievalContext | None = None,
    ) -> list[MemoryRecord]:
        """Retrieves memory using local-first routing and escalation."""
        return self.router.retrieve(query=query, filters=filters, limit=limit, context=context)
