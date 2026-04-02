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

from src.memory.types.base import TypedMemoryRecord


class ReflectionMemoryContent(BaseModel):
    """Represents the reflection memory content component."""
    reasoning: str | None = None
    improvement_suggestions: list[str] = Field(default_factory=list)
    failure_analysis: str | None = None
    summary: str | None = None


class ReflectionMemory(TypedMemoryRecord):
    """Represents reflection memory."""
    type: Literal["reflection"] = "reflection"
    layer: Literal["warm", "cold"] = "warm"
    scope: Literal["agent_local", "global"] = "agent_local"
    content: ReflectionMemoryContent | dict | str
    default_layer = "warm"
    default_scope = "agent_local"
