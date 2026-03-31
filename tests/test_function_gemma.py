"""Created: 2026-03-31

Purpose: Tests the function gemma behavior.
"""

from dataclasses import dataclass
from pathlib import Path

from LLM.function_gemma import FunctionGemmaLLM
from mailmind.agents.function_planner import FunctionCallingToolPlanner
from mailmind.agents.planner import RuleBasedToolPlanner
from mailmind.memory.conversation import ConversationMemory
from mailmind.storage.repository import SQLiteMessageRepository
from tools.base import BaseTool
from tools.catalog import build_tool_catalog_from_tools
from tools.registry import ToolRegistry
from pydantic import BaseModel


class SearchInput(BaseModel):
    sender: str | None = None


class SearchOutput(BaseModel):
    ok: bool = True


class SearchTool(BaseTool[SearchInput, SearchOutput]):
    name = "email_search"
    description = "Search emails."
    input_schema = SearchInput
    output_schema = SearchOutput

    def execute(self, input: SearchInput) -> SearchOutput:
        return SearchOutput()


@dataclass(slots=True)
class FakeFunctionGemma(FunctionGemmaLLM):
    def select_tool_call(self, *, user_input: str, tool_catalog: list[dict], memory_state: dict | None = None):
        del user_input, tool_catalog, memory_state
        return self._parse_function_call(
            "<start_function_call>call:email_search{sender:<escape>openai<escape>}<end_function_call>"
        )


def test_function_gemma_parser_extracts_tool_call() -> None:
    llm = FunctionGemmaLLM()
    call = llm._parse_function_call(
        "<start_function_call>call:email_search{sender:<escape>deepmind<escape>}<end_function_call>"
    )
    assert call.tool_name == "email_search"
    assert call.arguments["sender"] == "deepmind"


def test_tool_catalog_builds_function_schema() -> None:
    registry = ToolRegistry()
    registry.register(SearchTool())
    catalog = build_tool_catalog_from_tools(registry.list_tools())
    assert catalog[0]["function"]["name"] == "email_search"
    assert catalog[0]["function"]["parameters"]["type"] == "object"


def test_function_planner_uses_function_gemma_for_tool_selection(tmp_path: Path) -> None:
    repo = SQLiteMessageRepository(tmp_path / "planner.db")
    repo.init_db()
    memory = ConversationMemory.load("function-gemma", repo)
    registry = ToolRegistry()
    registry.register(SearchTool())
    planner = FunctionCallingToolPlanner(
        fallback=RuleBasedToolPlanner(),
        llm=FakeFunctionGemma(),
        tool_catalog=build_tool_catalog_from_tools(registry.list_tools()),
        enabled=True,
    )
    decision = planner.plan(user_input="emails from openai", memory=memory)
    assert decision.tool_call is not None
    assert decision.tool_call.tool_name == "email_search"
    assert decision.tool_call.arguments["sender"] == "openai"
