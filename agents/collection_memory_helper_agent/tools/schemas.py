"""Schemas for collection memory helper tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UpdateKeyEventMemoryInput(BaseModel):
    session_id: str
    user_id: str | None = None
    trigger: dict[str, Any] = Field(default_factory=dict)
    conversation_messages: list[dict[str, Any]] = Field(default_factory=list)
    conversation_state: dict[str, Any] = Field(default_factory=dict)


class UpdateKeyEventMemoryOutput(BaseModel):
    status: str
    user_id: str
    global_cues_updated: int
    conversation_outcome: str
    extracted_key_points: list[str] = Field(default_factory=list)
    user_summary: str
