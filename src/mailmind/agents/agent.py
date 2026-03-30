from __future__ import annotations

from dataclasses import dataclass

from mailmind.agents.base import BasePlanner
from mailmind.schemas.tools import AgentRunResult, ToolExecutionResult
from tools.executor import ToolExecutor


@dataclass(slots=True)
class Agent:
    planner: BasePlanner
    executor: ToolExecutor

    def run(self, query: str) -> dict:
        plan = self.planner.plan(query)
        results = [
            ToolExecutionResult.model_validate(self.executor.execute(step.tool_name, step.arguments))
            for step in plan.steps
        ]
        return AgentRunResult(plan=plan, results=results).model_dump(mode="json")
