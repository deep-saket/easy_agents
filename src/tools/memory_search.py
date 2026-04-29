"""Created: 2026-03-31

Purpose: Implements the memory search module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.schemas.tool_io import MemorySearchAttempt, MemorySearchInput, MemorySearchOutput
from src.tools.base import BaseTool


@dataclass(slots=True)
class MemorySearchTool(BaseTool[MemorySearchInput, MemorySearchOutput]):
    """Exposes long-term memory retrieval through the shared tool interface."""

    retriever: Any
    name: str = "memory_search"
    description: str = "Search layered long-term memory across hot, warm, and cold storage."
    input_schema = MemorySearchInput
    output_schema = MemorySearchOutput

    def execute(self, input: MemorySearchInput) -> MemorySearchOutput:
        """Searches memory and returns structured results.

        Args:
            input: Query text, optional filters, and a result limit.

        Returns:
            Structured memory search results.
        """
        queries = self._build_queries(input)
        merged: dict[str, Any] = {}
        attempts: list[MemorySearchAttempt] = []
        for query in queries:
            memories = self.retriever.retrieve(query=query, filters=input.filters, limit=input.limit)
            for memory in memories:
                merged[str(memory.id)] = memory
            attempts.append(
                MemorySearchAttempt(
                    query=query,
                    result_count=len(memories),
                    result_ids=[str(memory.id) for memory in memories],
                )
            )
            if input.stop_on_first_hit and memories:
                break
        merged_memories = list(merged.values())[: input.limit]
        selected_query = next((attempt.query for attempt in attempts if attempt.result_count > 0), None)
        if selected_query is None and attempts:
            selected_query = attempts[-1].query
        return MemorySearchOutput(
            total=len(merged_memories),
            memories=merged_memories,
            selected_query=selected_query,
            attempts=attempts,
        )

    @staticmethod
    def _build_queries(input: MemorySearchInput) -> list[str]:
        queries = [input.query.strip()] if input.query.strip() else []
        queries.extend(candidate.strip() for candidate in input.query_candidates if candidate.strip())
        if not queries:
            queries = [""]
        unique: list[str] = []
        seen: set[str] = set()
        for query in queries:
            key = query.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(query)
        return unique[: max(1, input.max_queries)]
