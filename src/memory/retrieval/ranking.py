"""Created: 2026-04-01

Purpose: Implements ranking helpers for layered memory retrieval.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.memory.models import MemoryRecord


def score_memory(record: MemoryRecord, query: str, filters: dict[str, object]) -> float:
    """Computes a ranking score for a memory record."""
    score = 0.0
    query_text = query.lower().strip()
    content_text = (record.content_text or "").lower()
    if query_text:
        score += content_text.count(query_text) * 5
        if query_text in str(record.normalized_metadata()).lower():
            score += 2
    if filters.get("scope") == record.scope:
        score += 4
    if filters.get("type") == record.type:
        score += 4
    if filters.get("agent_id") and filters["agent_id"] == record.agent_id:
        score += 3
    if filters.get("agent") and filters["agent"] == record.agent_id:
        score += 3
    if record.importance is not None:
        score += record.importance
    if record.confidence is not None:
        score += record.confidence * 2
    created_at = record.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_seconds = max((datetime.now(timezone.utc) - created_at).total_seconds(), 1.0)
    score += 10000 / age_seconds
    if record.layer == "hot":
        score += 5
    elif record.layer == "warm":
        score += 3
    return score
