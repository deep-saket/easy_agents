from __future__ import annotations

from dataclasses import dataclass

from LLM.huggingface import HuggingFaceLLM
from mailmind.agents.base import BasePlanner
from mailmind.schemas.tools import ToolCall, ToolPlan


@dataclass(slots=True)
class OptionalLLMToolPlanner(BasePlanner):
    fallback: BasePlanner
    llm: HuggingFaceLLM | None = None
    enabled: bool = False

    def plan(self, user_query: str) -> ToolPlan:
        if not self.enabled or self.llm is None:
            return self.fallback.plan(user_query)
        try:
            payload = self.llm.generate_json(
                "Return only JSON with a top-level `steps` array of tool calls. Each step must include `tool_name` and `arguments`.",
                f"User query: {user_query}",
            )
            return ToolPlan.model_validate(payload)
        except Exception:
            return self.fallback.plan(user_query)
