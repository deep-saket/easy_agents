from datetime import datetime, timezone

from mailmind.agents.planner import RuleBasedToolPlanner


def test_planner_maps_job_emails_today_to_search_tool() -> None:
    planner = RuleBasedToolPlanner()
    call = planner.plan("show me job emails today")
    assert call.steps[0].tool_name == "email_search"
    assert call.steps[0].arguments["category"] == "strong_ml_research_job"
    assert datetime.fromisoformat(call.steps[0].arguments["date_from"]).tzinfo == timezone.utc


def test_planner_maps_sender_queries() -> None:
    planner = RuleBasedToolPlanner()
    call = planner.plan("emails from deepmind")
    assert call.steps[0].tool_name == "email_search"
    assert call.steps[0].arguments["sender"] == "deepmind"
