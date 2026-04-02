"""Created: 2026-03-30

Purpose: Tests the agent planner behavior.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from src.agents.nodes import PlannerNode, ReactNode
from src.mailmind.agents.planner import RuleBasedToolPlanner
from src.mailmind.memory.conversation import ConversationMemory
from src.mailmind.storage.repository import DuckDBMessageRepository


def test_planner_maps_job_emails_today_to_search_tool(tmp_path) -> None:
    planner = RuleBasedToolPlanner()
    repo = DuckDBMessageRepository(tmp_path / "planner.db")
    repo.init_db()
    memory = ConversationMemory.load("planner-1", repo)
    decision = planner.plan(user_input="show me job emails today", memory=memory)
    assert decision.tool_call is not None
    assert decision.tool_call.tool_name == "email_search"
    assert decision.tool_call.arguments["category"] == "strong_ml_research_job"
    assert datetime.fromisoformat(decision.tool_call.arguments["date_from"]).tzinfo == timezone.utc


def test_planner_maps_sender_queries(tmp_path) -> None:
    planner = RuleBasedToolPlanner()
    repo = DuckDBMessageRepository(tmp_path / "planner.db")
    repo.init_db()
    memory = ConversationMemory.load("planner-2", repo)
    decision = planner.plan(user_input="emails from deepmind", memory=memory)
    assert decision.tool_call is not None
    assert decision.tool_call.tool_name == "email_search"
    assert decision.tool_call.arguments["sender"] == "deepmind"


def test_planner_node_renders_only_requested_context_into_system_prompt() -> None:
    class FakeLLM:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def generate(self, system_prompt: str, user_prompt: str) -> str:
            self.calls.append((system_prompt, user_prompt))
            return "84"

    llm = FakeLLM()
    node = PlannerNode(
        llm=llm,
        system_prompt="You are planning.",
    )

    decision = node.plan(
        user_input="What is 12 * (3 + 4)?",
        observation={"result": 84},
        available_tools=["calculator"],
        user_prompt=(
            "Question: What is 12 * (3 + 4)?\n"
            "Observation: {observation}\n"
            "Memory: {memory}\n"
            "Tools: {available_tools}"
        ),
    )

    assert decision.response_text == "84"
    assert llm.calls
    system_prompt, user_prompt = llm.calls[0]
    assert system_prompt == "You are planning."
    assert "Question: What is 12 * (3 + 4)?" in user_prompt
    assert 'Observation: {"result": 84}' in user_prompt
    assert "Tools: [\"calculator\"]" in user_prompt
    assert "Memory:" not in user_prompt


def test_planner_node_prefers_node_scoped_available_tools_over_state() -> None:
    class FakeLLM:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def generate(self, system_prompt: str, user_prompt: str) -> str:
            self.calls.append((system_prompt, user_prompt))
            return "ok"

    llm = FakeLLM()
    node = PlannerNode(
        llm=llm,
        system_prompt="You are planning.",
        user_prompt="Tools: {available_tools}",
        available_tools="node-tools-json",
    )

    decision = node.execute(
        {
            "user_input": "calculate",
            "available_tools": "state-tools-json",
            "steps": 0,
        }
    )

    assert decision["steps"] == 1
    assert llm.calls
    _, user_prompt = llm.calls[0]
    assert user_prompt == "Tools: node-tools-json"


def test_react_node_can_select_tool_without_delegate_planner() -> None:
    class FakeLLM:
        def generate(self, system_prompt: str, user_prompt: str) -> str:
            del system_prompt
            assert "tool_catalog_json" in user_prompt
            return (
                '{"tool_name": "calculate", "arguments": {"expression": "12 * (3 + 4)"}, '
                '"thought": "Use calculate."}'
            )

    node = ReactNode(
        llm=FakeLLM(),
        system_prompt="Choose one tool.",
        user_prompt='{"user_input": "{user_input}", "tool_catalog_json": {available_tools}}',
        available_tools='[{"type": "function", "function": {"name": "calculate"}}]',
    )

    decision = node.execute({"user_input": "What is 12 * (3 + 4)?", "steps": 0})

    assert decision["steps"] == 1
    assert decision["decision"].tool_call is not None
    assert decision["decision"].tool_call.tool_name == "calculate"
