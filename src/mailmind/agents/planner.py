from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from mailmind.agents.base import BasePlanner
from mailmind.schemas.tools import ToolCall, ToolPlan


@dataclass(slots=True)
class RuleBasedToolPlanner(BasePlanner):
    def plan(self, user_query: str) -> ToolPlan:
        query = user_query.strip().lower()
        now = datetime.now(timezone.utc)
        if "job emails today" in query or ("job" in query and "today" in query):
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
            return ToolPlan(
                steps=[
                    ToolCall(
                        tool_name="email_search",
                        arguments={
                            "category": "strong_ml_research_job",
                            "date_from": start.isoformat(),
                            "date_to": end.isoformat(),
                        },
                    )
                ]
            )
        if "events this week" in query or ("event" in query and "week" in query):
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            end = start + timedelta(days=7)
            return ToolPlan(
                steps=[
                    ToolCall(
                        tool_name="email_search",
                        arguments={
                            "category": "network_event",
                            "date_from": start.isoformat(),
                            "date_to": end.isoformat(),
                        },
                    )
                ]
            )
        if "fetch emails" in query or "fetch new emails" in query:
            return ToolPlan(steps=[ToolCall(tool_name="gmail_fetch", arguments={"process_messages": True})])
        if "summarize" in query and "email" in query:
            return ToolPlan(
                steps=[
                    ToolCall(tool_name="email_search", arguments={"query": user_query, "limit": 5}),
                ]
            )
        if query.startswith("emails from "):
            return ToolPlan(
                steps=[ToolCall(tool_name="email_search", arguments={"sender": query.removeprefix("emails from ").strip()})]
            )
        if "emails today" in query:
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
            return ToolPlan(
                steps=[ToolCall(tool_name="email_search", arguments={"date_from": start.isoformat(), "date_to": end.isoformat()})]
            )
        return ToolPlan(steps=[ToolCall(tool_name="email_search", arguments={"query": user_query})])
