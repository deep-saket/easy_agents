from __future__ import annotations

from dataclasses import dataclass

from llm.function_gemma import FunctionGemmaLLM
from mailmind.agents.base import BasePlanner
from mailmind.memory.conversation import ConversationMemory
from mailmind.schemas.tools import PlannerDecision


@dataclass(slots=True)
class FunctionCallingToolPlanner(BasePlanner):
    fallback: BasePlanner
    llm: FunctionGemmaLLM | None = None
    tool_catalog: list[dict] | None = None
    enabled: bool = False

    def plan(
        self,
        *,
        user_input: str,
        memory: ConversationMemory,
        observation: dict | None = None,
    ) -> PlannerDecision:
        if observation is not None or memory.state.get("pending_choice"):
            return self.fallback.plan(user_input=user_input, memory=memory, observation=observation)
        if not self.enabled or self.llm is None or not self.tool_catalog:
            return self.fallback.plan(user_input=user_input, memory=memory, observation=observation)
        try:
            tool_call = self.llm.select_tool_call(
                user_input=user_input,
                tool_catalog=self.tool_catalog,
                memory_state=memory.state,
            )
            return PlannerDecision(
                thought="Function Gemma selected the next tool.",
                tool_call=tool_call,
                respond_directly=False,
                done=False,
            )
        except Exception:
            return self.fallback.plan(user_input=user_input, memory=memory, observation=observation)
