"""Created: 2026-04-11

Purpose: Tests MailMind-specific router and formatter nodes.
"""

from agents.mailmind.nodes import (
    MailMindApprovalRouterNode,
    MailMindContextFormatterNode,
    MailMindEntryRouterNode,
)


def test_mailmind_entry_router_uses_trigger_type_when_present() -> None:
    node = MailMindEntryRouterNode()

    update = node.execute({"trigger_type": "scheduled_poll", "intent": {"intent": "query_mail"}})

    assert update["route"] == "poll"
    assert node.route(update) == "poll"


def test_mailmind_entry_router_falls_back_to_intent() -> None:
    node = MailMindEntryRouterNode()

    update = node.execute({"intent": {"intent": "approval_reply"}})

    assert update["route"] == "approval"


def test_mailmind_approval_router_detects_approve_and_redraft_paths() -> None:
    node = MailMindApprovalRouterNode()

    approve = node.execute({"user_input": "yes, go ahead and send it"})
    redraft = node.execute({"user_input": "please redraft this with a softer tone"})

    assert approve["route"] == "approve_send"
    assert redraft["route"] == "redraft"


def test_mailmind_approval_router_defaults_to_more_context() -> None:
    node = MailMindApprovalRouterNode()

    update = node.execute({"user_input": "can you explain this a bit more?"})

    assert update["route"] == "more_context"


def test_mailmind_context_formatter_builds_compact_response_text() -> None:
    node = MailMindContextFormatterNode()

    update = node.execute(
        {
            "observation": {"tool_name": "email_search", "output": {"total": 2}},
            "memory_context": {"semantic": [{"fact": "prefers research roles"}]},
        }
    )

    assert "Observation:" in update["response"]
    assert "Memory Context:" in update["response"]
    assert "email_search" in update["response"]
