"""Created: 2026-03-31

Purpose: Implements the error module for the shared memory platform layer.

Error memory

failures, bad outputs, wrong classifications, user corrections, tool failures
warm first-class storage
should influence future routing and tool choice
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.memory.types.base import TypedMemoryRecord


class ErrorMemoryContent(BaseModel):
    """Represents the error memory content component."""
    input: Any = Field(default_factory=dict)
    output: Any | None = None
    error_type: Literal["user_feedback", "reflection", "tool_failure"] = "tool_failure"
    correction: str | None = None
    root_cause: str | None = None
    agent: str = "unknown"


class ErrorMemory(TypedMemoryRecord):
    """Represents error memory."""
    type: Literal["error"] = "error"
    layer: Literal["warm", "cold"] = "warm"
    scope: Literal["agent_local", "global"] = "agent_local"
    content: ErrorMemoryContent
    default_layer = "warm"
    default_scope = "agent_local"
