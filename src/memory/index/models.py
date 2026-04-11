"""Created: 2026-04-10

Purpose: Defines memory-specific vector indexing models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IndexableMemoryRecord(BaseModel):
    """Represents one memory record prepared for vector indexing."""

    record_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexSearchHit(BaseModel):
    """Represents one memory-specific similarity hit."""

    record_id: str
    similarity: float
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["IndexSearchHit", "IndexableMemoryRecord"]
