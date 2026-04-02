"""Created: 2026-03-31

Purpose: Implements the react planner module for the shared planner platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.planner.base import BasePlanner


@dataclass(slots=True)
class ReActPlanner(BasePlanner):
    """Represents the re act planner component."""
    delegate: object

    def plan(self, user_input: str, memory, available_tools, observation=None):
        del available_tools
        return self.delegate.plan(user_input=user_input, memory=memory, observation=observation)

