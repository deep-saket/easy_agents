"""Created: 2026-04-11

Purpose: Implements MailMind-specific router nodes for the shared graph runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.nodes.base import BaseGraphNode
from src.nodes.types import AgentState, NodeUpdate


def _intent_name(state: AgentState) -> str:
    intent = state.get("intent") or {}
    if isinstance(intent, dict):
        return str(intent.get("intent", "")).strip().lower()
    return ""


@dataclass(slots=True)
class MailMindEntryRouterNode(BaseGraphNode):
    """Routes the top-level MailMind turn into poll, query, approval, or maintenance."""

    default_route: str = "query"

    def execute(self, state: AgentState) -> NodeUpdate:
        route = self._route_for_state(state)
        return {"route": route}

    def route(self, state: AgentState) -> str:
        return str(state.get("route", self.default_route))

    def _route_for_state(self, state: AgentState) -> str:
        trigger_type = str(state.get("trigger_type", "")).strip().lower()
        intent_name = _intent_name(state)

        if trigger_type in {"poll", "poll_inbox", "scheduled_poll", "inbox_poll"}:
            return "poll"
        if trigger_type in {"approval", "approval_reply"}:
            return "approval"
        if trigger_type in {"maintenance", "cron", "job"}:
            return "maintenance"
        if trigger_type in {"query", "message", "whatsapp"}:
            return "query"

        if intent_name == "poll_inbox":
            return "poll"
        if intent_name == "approval_reply":
            return "approval"
        if intent_name == "maintenance":
            return "maintenance"
        if intent_name == "query_mail":
            return "query"

        return self.default_route


@dataclass(slots=True)
class MailMindApprovalRouterNode(BaseGraphNode):
    """Routes approval reply turns into approve, reject, redraft, or more-context paths."""

    default_route: str = "more_context"

    def execute(self, state: AgentState) -> NodeUpdate:
        route = self._route_for_state(state)
        return {"route": route}

    def route(self, state: AgentState) -> str:
        return str(state.get("route", self.default_route))

    def _route_for_state(self, state: AgentState) -> str:
        text = str(state.get("user_input", "")).strip().lower()
        if not text:
            return self.default_route

        approve_keywords = {"approve", "approved", "yes", "send", "ok send", "go ahead"}
        reject_keywords = {"reject", "rejected", "no", "dont send", "do not send", "cancel"}
        redraft_keywords = {"redraft", "rewrite", "revise", "change draft", "edit draft"}
        context_keywords = {"why", "context", "details", "show more", "more context", "what happened"}

        if any(keyword in text for keyword in approve_keywords):
            return "approve_send"
        if any(keyword in text for keyword in reject_keywords):
            return "reject"
        if any(keyword in text for keyword in redraft_keywords):
            return "redraft"
        if any(keyword in text for keyword in context_keywords):
            return "more_context"
        return self.default_route


__all__ = ["MailMindApprovalRouterNode", "MailMindEntryRouterNode"]
