"""Created: 2026-04-10

Purpose: Defines reusable vector retrieval models shared by memory and future RAG features.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IndexedItem(BaseModel):
    """Represents one item written into a vector index backend."""

    item_id: str
    vector: list[float]
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalHit(BaseModel):
    """Represents one similarity-search hit from a vector backend."""

    item_id: str
    score: float
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["IndexedItem", "RetrievalHit"]
