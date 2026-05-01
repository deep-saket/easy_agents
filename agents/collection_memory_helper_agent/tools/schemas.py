"""Schemas for collection memory helper tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UpdateKeyEventMemoryInput(BaseModel):
    session_id: str
    trigger: dict[str, Any] = Field(default_factory=dict)
    conversation_messages: list[dict[str, Any]] = Field(default_factory=list)
    conversation_state: dict[str, Any] = Field(default_factory=dict)


class UpdateKeyEventMemoryOutput(BaseModel):
    status: str
    global_events_updated: int
    user_session_id: str
    extracted_key_events: list[str] = Field(default_factory=list)
    user_summary: str
