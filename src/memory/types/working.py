"""Created: 2026-03-31

Purpose: Implements the working module for the shared memory platform layer.

Working memory

short-lived
current chat state, pending clarification, selected email, last tool results
usually hot only
optionally checkpointed to warm for recovery

"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkingMemory(BaseModel):
    session_id: str
    current_goal: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    recent_items: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)
