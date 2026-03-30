from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from mailmind.schemas.tools import ToolCall


@dataclass(slots=True)
class ToolPlanner:
    def plan(self, user_query: str) -> ToolCall:
        query = user_query.strip().lower()
        now = datetime.now(timezone.utc)
        if "job emails today" in query or ("job" in query and "today" in query):
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
            return ToolCall(
                tool_name="email_search",
                arguments={
                    "category": "strong_ml_research_job",
                    "date_from": start.isoformat(),
                    "date_to": end.isoformat(),
                },
            )
        if "events this week" in query or ("event" in query and "week" in query):
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            end = start + timedelta(days=7)
            return ToolCall(
                tool_name="email_search",
                arguments={
                    "category": "network_event",
                    "date_from": start.isoformat(),
                    "date_to": end.isoformat(),
                },
            )
        if query.startswith("emails from "):
            return ToolCall(tool_name="email_search", arguments={"sender": query.removeprefix("emails from ").strip()})
        if "emails today" in query:
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
            return ToolCall(tool_name="email_search", arguments={"date_from": start.isoformat(), "date_to": end.isoformat()})
        return ToolCall(tool_name="email_search", arguments={"query": user_query})

