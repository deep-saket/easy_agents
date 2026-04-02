"""Created: 2026-03-30

Purpose: Implements the planner module for the shared mailmind platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from src.mailmind.agents.base import BasePlanner
from src.mailmind.memory.conversation import ConversationMemory
from src.mailmind.schemas.tools import PlannerDecision, ToolCall


@dataclass(slots=True)
class RuleBasedToolPlanner(BasePlanner):
    """Represents the rule based tool planner component."""
    def plan(
        self,
        *,
        user_input: str,
        memory: ConversationMemory | None = None,
        observation: dict | None = None,
        memory_context: dict[str, object] | None = None,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        available_tools: list[object] | None = None,
    ) -> PlannerDecision:
        del memory_context, system_prompt, user_prompt, available_tools
        if memory is None:
            raise ValueError("RuleBasedToolPlanner requires working memory for multi-turn state.")
        if observation is not None:
            return self._plan_from_observation(memory, observation)

        query = user_input.strip().lower()
        pending_filters = memory.state.get("last_search_filters", {})
        if memory.state.get("pending_choice"):
            category = self._infer_category(query)
            if category == "__all__":
                memory.clear_pending()
                return PlannerDecision(
                    thought="User asked for all emails from the previous result set.",
                    tool_call=ToolCall(tool_name="email_search", arguments=dict(pending_filters)),
                )
            if category is not None:
                filters = dict(pending_filters)
                filters["category"] = category
                memory.clear_pending()
                return PlannerDecision(
                    thought="User clarified the requested category.",
                    tool_call=ToolCall(tool_name="email_search", arguments=filters),
                )
            return PlannerDecision(
                thought="Waiting for clarification on which category of emails to show.",
                respond_directly=True,
                response_text="Do you want job emails, event emails, or all emails from the previous result?",
                done=True,
            )

        now = datetime.now(timezone.utc)
        if "job emails today" in query or ("job" in query and "today" in query):
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
            arguments = {
                "category": "strong_ml_research_job",
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
            }
            memory.set_state(last_search_filters=arguments, last_query_type="email_search")
            return PlannerDecision(
                thought="Search today's job emails.",
                tool_call=ToolCall(tool_name="email_search", arguments=arguments),
            )
        if "events this week" in query or ("event" in query and "week" in query):
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            end = start + timedelta(days=7)
            arguments = {
                "category": "network_event",
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
            }
            memory.set_state(last_search_filters=arguments, last_query_type="email_search")
            return PlannerDecision(
                thought="Search event emails for the coming week.",
                tool_call=ToolCall(tool_name="email_search", arguments=arguments),
            )
        if "fetch emails" in query or "fetch new emails" in query:
            return PlannerDecision(
                thought="Fetch and process new emails before answering.",
                tool_call=ToolCall(tool_name="gmail_fetch", arguments={"process_messages": True}),
            )
        if query.startswith("emails from "):
            arguments = {"sender": query.removeprefix("emails from ").strip()}
            memory.set_state(last_search_filters=arguments, last_query_type="email_search")
            return PlannerDecision(
                thought="Search emails by sender.",
                tool_call=ToolCall(tool_name="email_search", arguments=arguments),
            )
        if "what emails today" in query or "what emails did i get today" in query or "emails today" in query:
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
            arguments = {"date_from": start.isoformat(), "date_to": end.isoformat(), "limit": 100}
            memory.set_state(last_search_filters=arguments, last_query_type="email_summary")
            return PlannerDecision(
                thought="Search all emails from today, then summarize if there are multiple results.",
                tool_call=ToolCall(tool_name="email_search", arguments=arguments),
            )
        if "job emails" in query or query == "job ones":
            arguments = {"category": "strong_ml_research_job"}
            memory.set_state(last_search_filters=arguments, last_query_type="email_search")
            return PlannerDecision(
                thought="Search job-related emails.",
                tool_call=ToolCall(tool_name="email_search", arguments=arguments),
            )
        if "event emails" in query or "event ones" in query:
            arguments = {"category": "network_event"}
            memory.set_state(last_search_filters=arguments, last_query_type="email_search")
            return PlannerDecision(
                thought="Search event-related emails.",
                tool_call=ToolCall(tool_name="email_search", arguments=arguments),
            )
        arguments = {"query": user_input}
        memory.set_state(last_search_filters=arguments, last_query_type="email_search")
        return PlannerDecision(
            thought="Use the search tool for the free-form email query.",
            tool_call=ToolCall(tool_name="email_search", arguments=arguments),
        )

    def _plan_from_observation(self, memory: ConversationMemory, observation: dict) -> PlannerDecision:
        tool_name = observation["tool_name"]
        output = observation["output"]
        if tool_name == "email_search":
            if output["total"] == 0:
                memory.clear_pending()
                return PlannerDecision(
                    thought="No emails matched the query.",
                    respond_directly=True,
                    response_text="I didn’t find any matching emails.",
                    done=True,
                )
            if memory.state.get("last_query_type") == "email_summary" and output["total"] > 1 and not observation["output"].get("query_category"):
                message_ids = [email["id"] for email in output["emails"]]
                return PlannerDecision(
                    thought="Broad result set found, summarize categories before responding.",
                    tool_call=ToolCall(tool_name="email_summary", arguments={"message_ids": message_ids, "max_items": 5}),
                )
            memory.clear_pending()
            return PlannerDecision(
                thought="Search results are narrow enough to answer directly.",
                respond_directly=True,
                response_text=self._format_email_list(output["emails"]),
                done=True,
            )
        if tool_name == "email_summary":
            memory.set_state(pending_choice=True, last_query_type="email_summary")
            return PlannerDecision(
                thought="Provide a summary and ask the user to narrow the category.",
                respond_directly=True,
                response_text=self._format_summary(output),
                done=True,
            )
        return PlannerDecision(
            thought="Tool finished; send a short acknowledgement.",
            respond_directly=True,
            response_text="Done.",
            done=True,
        )

    @staticmethod
    def _infer_category(query: str) -> str | None:
        if "job" in query:
            return "strong_ml_research_job"
        if "event" in query:
            return "network_event"
        if "all" in query:
            return "__all__"
        return None

    @staticmethod
    def _format_summary(output: dict) -> str:
        lines = [f"You got {output['total']} emails in that set:"]
        for category, count in output["categories"].items():
            pretty = category.replace("_", " ")
            lines.append(f"- {count} {pretty}")
        lines.append("")
        lines.append("Do you want:")
        lines.append("1. Job emails")
        lines.append("2. Event emails")
        lines.append("3. All emails")
        return "\n".join(lines)

    @staticmethod
    def _format_email_list(emails: list[dict]) -> str:
        lines = [f"I found {len(emails)} matching emails:"]
        for email in emails[:5]:
            lines.append(f"- {email['subject']} from {email['from_email']}")
        if len(emails) > 5:
            lines.append(f"- and {len(emails) - 5} more")
        return "\n".join(lines)
