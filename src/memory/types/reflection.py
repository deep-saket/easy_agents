"""Created: 2026-03-31

Purpose: Implements the reflection module for the shared memory platform layer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from memory.models import MemoryItem


class ReflectionMemoryContent(BaseModel):
    reasoning: str | None = None
    improvement_suggestions: list[str] = Field(default_factory=list)
    failure_analysis: str | None = None
    summary: str | None = None


class ReflectionMemory(MemoryItem):
    type: Literal["reflection"] = "reflection"
    content: ReflectionMemoryContent | dict | str
