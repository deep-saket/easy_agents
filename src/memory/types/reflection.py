"""Created: 2026-03-31

Purpose: Implements the reflection module for the shared memory platform layer.

Reflection memory

post-hoc analysis
why output failed, what should improve, compressed lessons from episodes
warm, can promote into semantic memory
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.memory.models import MemoryItem


class ReflectionMemoryContent(BaseModel):
    reasoning: str | None = None
    improvement_suggestions: list[str] = Field(default_factory=list)
    failure_analysis: str | None = None
    summary: str | None = None


class ReflectionMemory(MemoryItem):
    type: Literal["reflection"] = "reflection"
    content: ReflectionMemoryContent | dict | str
