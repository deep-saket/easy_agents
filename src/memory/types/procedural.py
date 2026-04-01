"""Created: 2026-03-31

Purpose: Implements the procedural module for the shared memory platform layer.

Procedural memory

how the system acts
tools, prompts, policies, planners, routing rules
not runtime memory records by default
stored as code + config, not in DuckDB as ordinary memory rows
can have procedural metadata tables for versioning/audit
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProceduralMemory(BaseModel):
    tool_names: list[str] = Field(default_factory=list)
    planner_names: list[str] = Field(default_factory=list)
    prompt_names: list[str] = Field(default_factory=list)
