"""Created: 2026-04-10

Purpose: Provides generic helpers for merging and ranking hybrid retrieval results.
"""

from __future__ import annotations

from src.retrieval.models import RetrievalHit


def merge_retrieval_hits(*groups: list[RetrievalHit], limit: int = 20) -> list[RetrievalHit]:
    """Merges hit groups by item id, keeping the highest score for duplicates."""

    merged: dict[str, RetrievalHit] = {}
    for group in groups:
        for hit in group:
            current = merged.get(hit.item_id)
            if current is None or hit.score > current.score:
                merged[hit.item_id] = hit
    return sorted(merged.values(), key=lambda hit: hit.score, reverse=True)[:limit]


__all__ = ["merge_retrieval_hits"]
