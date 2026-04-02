"""Created: 2026-03-31

Purpose: Implements the messages module for the shared schemas platform layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConversationMessage(BaseModel):
    """Represents the conversation message component."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    role: str
    content: str
    created_at: datetime = Field(default_factory=utc_now)


__all__ = ["ConversationMessage"]
