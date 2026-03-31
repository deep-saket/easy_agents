"""Created: 2026-03-31

Purpose: Implements the models module for the shared memory platform layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


MemoryType = Literal["semantic", "episodic", "error", "reflection", "task"]
MemoryLayerName = Literal["hot", "warm", "cold"]
MemoryPriority = Literal["low", "medium", "high"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: MemoryType
    layer: MemoryLayerName
    content: Any
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    def normalized_metadata(self) -> dict[str, Any]:
        metadata = dict(self.metadata)
        metadata.setdefault("agent", "unknown")
        metadata.setdefault("tags", [])
        metadata.setdefault("source", "system")
        metadata.setdefault("priority", "medium")
        return metadata


class MemoryQuery(BaseModel):
    query: str = ""
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = 20


class MemorySearchResult(BaseModel):
    memories: list[MemoryItem]
    total: int


class SleepingTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    task_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    created_at: datetime = Field(default_factory=utc_now)
