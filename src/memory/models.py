"""Created: 2026-04-01

Purpose: Defines the config-aware memory record and retrieval models.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


MemoryType = Literal["working", "episodic", "semantic", "error", "reflection", "task"]
MemoryLayerName = Literal["hot", "warm", "cold"]
MemoryScope = Literal["agent_local", "global"]
MemoryPriority = Literal["low", "medium", "high"]


def utc_now() -> datetime:
    """Returns the current UTC timestamp."""
    return datetime.now(timezone.utc)


class RetrievalContext(BaseModel):
    """Carries state used by the memory router for escalation decisions."""

    agent_id: str | None = None
    step_count: int = 0
    confidence: float = 1.0
    last_error: bool = False
    allow_global: bool = True


class MemoryRecord(BaseModel):
    """Represents one structured memory row across hot, warm, and cold layers.

    The model keeps backward-compatible `content` and `metadata` fields for the
    existing platform while also exposing explicit fields required by the new
    DuckDB-backed architecture: `scope`, `agent_id`, `content_text`,
    `content_json`, provenance fields, and lifecycle timestamps.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str | None = None
    scope: MemoryScope = "agent_local"
    type: MemoryType
    layer: MemoryLayerName
    content: Any = None
    content_text: str | None = None
    content_json: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    source_type: str | None = None
    source_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    importance: float | None = None
    confidence: float | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime | None = None
    archived_at: datetime | None = None

    @model_validator(mode="after")
    def _sync_content_fields(self) -> "MemoryRecord":
        """Normalizes convenience fields into a consistent record shape."""
        if self.content_json is None and isinstance(self.content, BaseModel):
            self.content_json = self.content.model_dump(mode="json")
        elif self.content_json is None and isinstance(self.content, (dict, list)):
            self.content_json = self.content
        elif self.content_json is None and self.content is not None:
            self.content_json = self.content
        if self.content_text is None:
            if isinstance(self.content, str):
                self.content_text = self.content
            elif self.content is not None:
                self.content_text = str(self.content)
            elif self.content_json is not None:
                self.content_text = str(self.content_json)
        if self.agent_id is None:
            self.agent_id = self.metadata.get("agent_id") or self.metadata.get("agent")
        if not self.tags and isinstance(self.metadata.get("tags"), list):
            self.tags = [str(tag) for tag in self.metadata["tags"]]
        if self.source_type is None:
            self.source_type = self.metadata.get("source_type") or self.metadata.get("source")
        if self.source_id is None:
            self.source_id = self.metadata.get("source_id")
        if self.importance is None and self.metadata.get("importance") is not None:
            self.importance = float(self.metadata["importance"])
        if self.confidence is None and self.metadata.get("confidence") is not None:
            self.confidence = float(self.metadata["confidence"])
        return self

    @property
    def memory_type(self) -> MemoryType:
        """Returns the logical memory type."""
        return self.type

    def normalized_metadata(self) -> dict[str, Any]:
        """Returns a metadata payload enriched with normalized defaults."""
        metadata = dict(self.metadata)
        metadata.setdefault("agent", self.agent_id or "unknown")
        metadata.setdefault("agent_id", self.agent_id or metadata["agent"])
        metadata.setdefault("tags", list(self.tags))
        metadata.setdefault("source", self.source_type or "system")
        metadata.setdefault("source_type", self.source_type or metadata["source"])
        metadata.setdefault("source_id", self.source_id)
        priority = metadata.get("priority", "medium")
        if priority not in {"low", "medium", "high"}:
            priority = "medium"
        metadata["priority"] = priority
        metadata.setdefault("importance", self.importance)
        metadata.setdefault("confidence", self.confidence)
        metadata.setdefault("scope", self.scope)
        return metadata


class MemoryItem(MemoryRecord):
    """Backward-compatible alias model for existing imports."""


class MemoryQuery(BaseModel):
    """Defines a structured memory search request."""

    query: str = ""
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = 20
    context: RetrievalContext | None = None


class MemorySearchResult(BaseModel):
    """Represents a structured memory search response."""

    memories: list[MemoryRecord]
    total: int


class SleepingTask(BaseModel):
    """Represents a deferred memory maintenance task."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    task_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    created_at: datetime = Field(default_factory=utc_now)
