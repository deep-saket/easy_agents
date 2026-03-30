from datetime import datetime, timezone

from mailmind.agents.planner import ToolPlanner


def test_planner_maps_job_emails_today_to_search_tool() -> None:
    planner = ToolPlanner()
    call = planner.plan("show me job emails today")
    assert call.tool_name == "email_search"
    assert call.arguments["category"] == "strong_ml_research_job"
    assert datetime.fromisoformat(call.arguments["date_from"]).tzinfo == timezone.utc


def test_planner_maps_sender_queries() -> None:
    planner = ToolPlanner()
    call = planner.plan("emails from deepmind")
    assert call.tool_name == "email_search"
    assert call.arguments["sender"] == "deepmind"
