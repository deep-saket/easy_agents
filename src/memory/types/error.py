"""Created: 2026-03-31

Purpose: Implements the error module for the shared memory platform layer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from memory.models import MemoryItem


class ErrorMemoryContent(BaseModel):
    input: Any = Field(default_factory=dict)
    output: Any | None = None
    error_type: Literal["user_feedback", "reflection", "tool_failure"] = "tool_failure"
    correction: str | None = None
    root_cause: str | None = None
    agent: str = "unknown"


class ErrorMemory(MemoryItem):
    type: Literal["error"] = "error"
    content: ErrorMemoryContent
