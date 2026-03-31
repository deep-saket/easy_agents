from datetime import datetime, timezone
from mailmind.agents.planner import RuleBasedToolPlanner
from mailmind.memory.conversation import ConversationMemory
from mailmind.storage.repository import SQLiteMessageRepository


def test_planner_maps_job_emails_today_to_search_tool(tmp_path) -> None:
    planner = RuleBasedToolPlanner()
    repo = SQLiteMessageRepository(tmp_path / "planner.db")
    repo.init_db()
    memory = ConversationMemory.load("planner-1", repo)
    decision = planner.plan(user_input="show me job emails today", memory=memory)
    assert decision.tool_call is not None
    assert decision.tool_call.tool_name == "email_search"
    assert decision.tool_call.arguments["category"] == "strong_ml_research_job"
    assert datetime.fromisoformat(decision.tool_call.arguments["date_from"]).tzinfo == timezone.utc


def test_planner_maps_sender_queries(tmp_path) -> None:
    planner = RuleBasedToolPlanner()
    repo = SQLiteMessageRepository(tmp_path / "planner.db")
    repo.init_db()
    memory = ConversationMemory.load("planner-2", repo)
    decision = planner.plan(user_input="emails from deepmind", memory=memory)
    assert decision.tool_call is not None
    assert decision.tool_call.tool_name == "email_search"
    assert decision.tool_call.arguments["sender"] == "deepmind"
