from dataclasses import dataclass

from LLM.huggingface import HuggingFaceLLM
from mailmind.agents.llm_planner import OptionalLLMToolPlanner
from mailmind.agents.planner import RuleBasedToolPlanner


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


def test_llm_planner_returns_structured_plan() -> None:
    planner = OptionalLLMToolPlanner(fallback=RuleBasedToolPlanner(), llm=FakePlannerLLM(), enabled=True)
    plan = planner.plan("show me emails from openai")
    assert plan.steps[0].tool_name == "email_search"
    assert plan.steps[0].arguments["sender"] == "openai"
