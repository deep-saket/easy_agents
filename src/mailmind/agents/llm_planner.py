from __future__ import annotations

from dataclasses import dataclass

from llm.huggingface import HuggingFaceLLM
from mailmind.agents.base import BasePlanner
from mailmind.memory.conversation import ConversationMemory
from mailmind.schemas.tools import PlannerDecision, ToolCall


@dataclass(slots=True)
class OptionalLLMToolPlanner(BasePlanner):
    fallback: BasePlanner
    llm: HuggingFaceLLM | None = None
    enabled: bool = False

    def plan(
        self,
        *,
        user_input: str,
        memory: ConversationMemory,
        observation: dict | None = None,
    ) -> PlannerDecision:
        if not self.enabled or self.llm is None:
            return self.fallback.plan(user_input=user_input, memory=memory, observation=observation)
        try:
            payload = self.llm.generate_json(
                "Return only JSON with keys thought, tool_call, respond_directly, response_text, done. "
                "tool_call must contain tool_name and arguments when present.",
                f"User query: {user_input}\nObservation: {observation}\nMemory state: {memory.state}",
            )
            if "steps" in payload and payload["steps"]:
                first_step = payload["steps"][0]
                payload = {
                    "thought": "LLM selected a tool.",
                    "tool_call": first_step,
                    "respond_directly": False,
                    "done": False,
                }
            return PlannerDecision.model_validate(payload)
        except Exception:
            return self.fallback.plan(user_input=user_input, memory=memory, observation=observation)
