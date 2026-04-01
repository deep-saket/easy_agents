"""Created: 2026-03-30

Purpose: Implements the llm planner module for the shared mailmind platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.llm.huggingface import HuggingFaceLLM
from src.mailmind.agents.base import BasePlanner
from src.mailmind.memory.conversation import ConversationMemory
from src.mailmind.schemas.tools import PlannerDecision, ToolCall


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
        memory_context: dict[str, object] | None = None,
    ) -> PlannerDecision:
        if not self.enabled or self.llm is None:
            return self.fallback.plan(
                user_input=user_input,
                memory=memory,
                observation=observation,
                memory_context=memory_context,
            )
        try:
            payload = self.llm.generate_json(
                "Return only JSON with keys thought, tool_call, respond_directly, response_text, done. "
                "tool_call must contain tool_name and arguments when present.",
                f"User query: {user_input}\nObservation: {observation}\nMemory state: {memory.state}\nMemory context: {memory_context}",
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
            return self.fallback.plan(
                user_input=user_input,
                memory=memory,
                observation=observation,
                memory_context=memory_context,
            )
