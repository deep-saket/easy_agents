"""Created: 2026-03-30

Purpose: Tests the llm planner behavior.
"""

from dataclasses import dataclass
from LLM.huggingface import HuggingFaceLLM
from mailmind.agents.llm_planner import OptionalLLMToolPlanner
from mailmind.agents.planner import RuleBasedToolPlanner
from mailmind.memory.conversation import ConversationMemory
from mailmind.storage.repository import SQLiteMessageRepository


@dataclass(slots=True)
class FakePlannerLLM(HuggingFaceLLM):
    model_name: str = "fake/model"

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        return {
            "steps": [
                {
                    "tool_name": "email_search",
                    "arguments": {"sender": "openai"},
                }
            ]
        }


def test_llm_planner_returns_structured_plan(tmp_path) -> None:
    planner = OptionalLLMToolPlanner(fallback=RuleBasedToolPlanner(), llm=FakePlannerLLM(), enabled=True)
    repo = SQLiteMessageRepository(tmp_path / "llm_planner.db")
    repo.init_db()
    memory = ConversationMemory.load("llm-planner-1", repo)
    decision = planner.plan(user_input="show me emails from openai", memory=memory)
    assert decision.tool_call is not None
    assert decision.tool_call.tool_name == "email_search"
    assert decision.tool_call.arguments["sender"] == "openai"
