from __future__ import annotations

from dataclasses import dataclass

from mailmind.agents.planner import ToolPlanner
from mailmind.tools.executor import ToolExecutor


@dataclass(slots=True)
class Agent:
    planner: ToolPlanner
    executor: ToolExecutor

    def run(self, query: str) -> dict:
        plan = self.planner.plan(query)
        return self.executor.execute(plan.tool_name, plan.arguments)
