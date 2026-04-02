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
    """Represents working memory."""
    session_id: str
    current_goal: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    recent_items: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)

    def add_message(self, *, role: str, content: str) -> None:
        """Appends one conversational item to recent working memory."""
        self.recent_items.append({"role": role, "content": content})
        self.recent_items[:] = self.recent_items[-6:]
        self.updated_at = utc_now()

    def add_user_message(self, content: str) -> None:
        """Appends one user message to working memory."""
        self.add_message(role="user", content=content)

    def add_agent_message(self, content: str) -> None:
        """Appends one agent message to working memory."""
        self.add_message(role="agent", content=content)

    def set_state(self, **kwargs: object) -> None:
        """Merges state updates into working memory."""
        self.state.update(kwargs)
        self.updated_at = utc_now()
