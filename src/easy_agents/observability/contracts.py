"""Versioned contracts for correlated agent-fleet events."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Severity(str, Enum):
    """Operational importance used by filters and alerts."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DataClassification(str, Enum):
    """Highest data sensitivity represented by an event."""

    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"
    CONFIDENTIAL = "confidential"
    SENSITIVE = "sensitive"


class EntityReference(BaseModel):
    """Stable reference to a Constellation or operational entity."""

    model_config = ConfigDict(frozen=True)

    kind: str = Field(min_length=1, max_length=64)
    id: str = Field(min_length=1, max_length=200)


class TraceEvent(BaseModel):
    """One immutable, redacted lifecycle fact in the local event log."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=1, ge=1, le=1)
    event_id: str = Field(default_factory=lambda: f"evt-{uuid4()}", min_length=1)
    sequence: int | None = Field(default=None, ge=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", max_length=120)
    severity: Severity = Severity.INFO
    status: str | None = Field(default=None, max_length=64)
    mission_id: str | None = Field(default=None, max_length=200)
    work_order_id: str | None = Field(default=None, max_length=200)
    run_id: str | None = Field(default=None, max_length=200)
    trace_id: str | None = Field(default=None, max_length=200)
    span_id: str | None = Field(default=None, max_length=200)
    parent_span_id: str | None = Field(default=None, max_length=200)
    actor: EntityReference | None = None
    subject: EntityReference | None = None
    summary: str = Field(min_length=1, max_length=500)
    duration_ms: float | None = Field(default=None, ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, int | float | None] = Field(default_factory=dict)
    data_classification: DataClassification = DataClassification.INTERNAL
    redaction_version: int = Field(default=1, ge=1)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Normalizes timestamps to timezone-aware UTC."""

        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class EventFilter(BaseModel):
    """Bounded event-history filter used by the store and HTTP API."""

    after_sequence: int = Field(default=0, ge=0)
    before_sequence: int | None = Field(default=None, ge=1)
    limit: int = Field(default=200, ge=1, le=2_000)
    mission_id: str | None = None
    run_id: str | None = None
    event_type: str | None = None
    status: str | None = None
    severity: Severity | None = None
    entity_kind: str | None = None
    entity_id: str | None = None
