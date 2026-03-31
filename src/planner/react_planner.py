from __future__ import annotations

from dataclasses import dataclass

from planner.base import BasePlanner


@dataclass(slots=True)
class ReActPlanner(BasePlanner):
    delegate: object

    def plan(self, user_input: str, memory, available_tools, observation=None):
        del available_tools
        return self.delegate.plan(user_input=user_input, memory=memory, observation=observation)

