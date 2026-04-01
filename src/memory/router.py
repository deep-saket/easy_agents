"""Created: 2026-04-01

Purpose: Implements local-first memory retrieval with global escalation.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.models import MemoryRecord, RetrievalContext
from src.memory.retrieval.ranking import score_memory


@dataclass(slots=True)
class MemoryRouter:
    """Routes memory retrieval from local storage to global fallback when needed."""

    local_retriever: object
    global_retriever: object
    escalation_step_count: int = 3
    confidence_threshold: float = 0.5

    def retrieve(
        self,
        query: str,
        filters: dict[str, object] | None = None,
        limit: int = 20,
        context: RetrievalContext | None = None,
    ) -> list[MemoryRecord]:
        filters = filters or {}
        context = context or RetrievalContext()
        local_results = self.local_retriever.retrieve(query=query, filters=filters, limit=limit)
        if self.should_escalate(local_results, context):
            global_filters = dict(filters)
            global_filters["scope"] = "global"
            global_results = self.global_retriever.retrieve(query=query, filters=global_filters, limit=limit)
            return self.merge(query, filters, local_results, global_results, limit=limit)
        return local_results

    def should_escalate(self, results: list[MemoryRecord], context: RetrievalContext) -> bool:
        """Determines whether retrieval should escalate to shared global memory."""
        return (
            len(results) == 0
            or context.step_count >= self.escalation_step_count
            or context.confidence < self.confidence_threshold
            or context.last_error is True
        ) and context.allow_global

    @staticmethod
    def merge(
        query: str,
        filters: dict[str, object],
        local_results: list[MemoryRecord],
        global_results: list[MemoryRecord],
        *,
        limit: int,
    ) -> list[MemoryRecord]:
        """Merges and ranks local and global retrieval results."""
        merged: dict[str, MemoryRecord] = {}
        for record in local_results + global_results:
            merged[record.id] = record
        return sorted(merged.values(), key=lambda record: score_memory(record, query, filters), reverse=True)[:limit]
