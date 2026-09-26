"""Behavior matrix for model-planned natural-language Galaxy Chat.

The model double supplies plans rather than relying on production keywords. Each
test therefore exercises the same typed validation, Charter authorization,
execution, tracing, response, and API serialization used with local Gemma.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from fastapi.testclient import TestClient

from easy_agents.constellation.api import create_app
from easy_agents.constellation.chat import ConversationStore
from easy_agents.constellation.commons_runtime import ApprovalCreate, CommonsRuntime


def _plan(
    circle_id: str,
    planet_id: str,
    action: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Builds one model-shaped plan used by the scripted inference double."""

    return {
        "circle_id": circle_id,
        "planet_id": planet_id,
        "actions": [
            {
                "action": action,
                "arguments": arguments or {},
                "reason": "The model selected the requested bounded operation.",
            }
        ],
        "reasoning_summary": "Model-selected behavior-matrix plan.",
    }


class ScriptedGemma:
    """Ready Gemma-shaped double that returns an explicit sequence of plans."""

    model_name = "gemma-4-E4B"
    base_url = "http://127.0.0.1:8080"

    def __init__(self, plans: list[dict[str, Any]]) -> None:
        self.plans = deque(plans)
        self.planning_calls = 0
        self.answer_calls = 0

    @staticmethod
    def is_ready() -> bool:
        return True

    @staticmethod
    def list_models() -> list[str]:
        return ["gemma-4-E4B"]

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        del system_prompt, user_prompt
        self.planning_calls += 1
        return self.plans.popleft()

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        del system_prompt, user_prompt
        self.answer_calls += 1
        return "The selected Planet completed its bounded response."


def _chat(client: TestClient, message: str) -> dict[str, Any]:
    response = client.post("/api/v2/wormhole/chat", json={"message": message})
    assert response.status_code == 200, response.text
    return response.json()


def test_model_planned_chat_behavior_matrix() -> None:
    """Exercises every supported action family through natural-language Chat."""

    commons = CommonsRuntime()
    approval = commons.create_approval(
        ApprovalCreate(
            mission_id="mission-needs-approval",
            effects=("send",),
            rationale="A human must decide before any external send.",
        )
    )
    plans = [
        _plan("venture_exploration", "opportunity_portfolio_steward", "respond"),
        _plan("commons", "personal_steward", "calculate", {"expression": "12*7"}),
        _plan(
            "commons",
            "personal_steward",
            "unit_convert",
            {"value": 5, "from_unit": "miles", "to_unit": "km"},
        ),
        _plan(
            "commons",
            "personal_steward",
            "memory_write",
            {"content": "Mom prefers a Sunday evening call", "tags": ["family"]},
        ),
        _plan(
            "commons",
            "personal_steward",
            "memory_search",
            {"query": "Sunday call", "limit": 5},
        ),
        _plan(
            "life_admin",
            "digital_librarian",
            "artifact_create",
            {"name": "Battery memo", "kind": "memo", "content": "Sodium is promising."},
        ),
        _plan("life_admin", "digital_librarian", "artifact_list"),
        _plan(
            "science_lab",
            "knowledge_librarian",
            "knowledge_add",
            {"title": "Battery note", "content": "Sodium batteries use abundant sodium."},
        ),
        _plan(
            "science_lab",
            "knowledge_librarian",
            "knowledge_search",
            {"query": "abundant sodium", "limit": 5},
        ),
        _plan(
            "science_lab",
            "knowledge_librarian",
            "knowledge_summarize",
            {"query": "sodium batteries", "limit": 5},
        ),
        _plan(
            "science_lab",
            "knowledge_librarian",
            "knowledge_verify",
            {"claims": ["Sodium batteries use abundant sodium"]},
        ),
        _plan(
            "commons",
            "safety_steward",
            "review_create",
            {"title": "Review battery thesis", "due_at": "2030-10-03T09:00:00+05:30"},
        ),
        _plan("commons", "safety_steward", "review_list"),
        _plan(
            "life_admin",
            "schedule_coordinator",
            "calendar_propose",
            {
                "title": "Call Mom",
                "starts_at": "2030-10-03T18:00:00+05:30",
                "ends_at": "2030-10-03T19:00:00+05:30",
            },
        ),
        _plan("life_admin", "schedule_coordinator", "calendar_list"),
        _plan("commons", "personal_steward", "approval_list", {"status": "pending"}),
        _plan(
            "commons",
            "personal_steward",
            "approval_decide",
            {
                "approval_id": approval.id,
                "decision": "rejected",
                "decided_by": "local_user",
            },
        ),
        _plan("commons", "safety_steward", "commons_status"),
    ]
    model = ScriptedGemma(plans)
    client = TestClient(
        create_app(
            gemma_client=model,
            chat_history=ConversationStore(),
            commons_runtime=commons,
        )
    )
    messages = [
        "Help me compare energy startup opportunities.",
        "Work out twelve times seven.",
        "How many kilometres are five miles?",
        "Keep in mind that Mom prefers a Sunday evening call.",
        "What did I tell you about Sunday calls?",
        "Create a battery memo with the supplied sentence.",
        "Show my artifacts.",
        "Add this battery note to my local knowledge.",
        "Search my evidence for abundant sodium.",
        "Summarize my sodium-battery evidence.",
        "Check this sodium claim against my sources.",
        "Schedule a review of my battery thesis.",
        "Show my scheduled reviews.",
        "Put a call with Mom on my local calendar.",
        "Show my local calendar.",
        "What approvals are waiting?",
        "Reject that pending external-send approval.",
        "Is Commons healthy?",
    ]

    results = [_chat(client, message) for message in messages]

    assert [item["planning"]["action_names"][0] for item in results] == [
        "respond",
        "calculate",
        "unit_convert",
        "memory_write",
        "memory_search",
        "artifact_create",
        "artifact_list",
        "knowledge_add",
        "knowledge_search",
        "knowledge_summarize",
        "knowledge_verify",
        "review_create",
        "review_list",
        "calendar_propose",
        "calendar_list",
        "approval_list",
        "approval_decide",
        "commons_status",
    ]
    assert results[0]["action_invocations"] == []
    assert results[1]["action_invocations"][0]["output"]["result"] == 84
    assert results[2]["action_invocations"][0]["output"]["converted_value"] == 8.04672
    assert "Sunday evening call" in results[4]["answer"]
    assert results[6]["action_invocations"][0]["output"]["artifacts"][0]["name"] == "Battery memo"
    assert results[8]["action_invocations"][0]["output"]["hits"]
    assert results[9]["action_invocations"][0]["output"]["citations"]
    assert results[10]["action_invocations"][0]["output"]["assessments"][0]["status"] == "supported"
    assert len(results[12]["action_invocations"][0]["output"]["reviews"]) == 1
    assert len(results[14]["action_invocations"][0]["output"]["items"]) == 1
    assert results[15]["action_invocations"][0]["output"]["approvals"][0]["id"] == approval.id
    assert results[16]["action_invocations"][0]["output"]["status"] == "rejected"
    assert results[17]["action_invocations"][0]["output"]["external_effects"] is False
    assert model.planning_calls == len(messages)
    assert model.answer_calls == len(messages)


def test_model_can_select_multiple_actions_without_rule_planning() -> None:
    plan = {
        "circle_id": "commons",
        "planet_id": "safety_steward",
        "actions": [
            {
                "action": "memory_write",
                "arguments": {"content": "The satcom idea uses optical links"},
                "reason": "Retain the supplied idea.",
            },
            {
                "action": "review_create",
                "arguments": {
                    "title": "Review satcom idea",
                    "due_at": "2030-10-03T09:00:00+05:30",
                },
                "reason": "Create the requested scheduled review.",
            },
        ],
        "reasoning_summary": "The user explicitly requested two local operations.",
    }
    model = ScriptedGemma([plan])
    client = TestClient(
        create_app(gemma_client=model, chat_history=ConversationStore())
    )

    payload = _chat(
        client,
        "Remember that the satcom idea uses optical links and schedule a review.",
    )

    assert payload["planning"]["action_names"] == ["memory_write", "review_create"]
    assert [item["action"] for item in payload["action_invocations"]] == [
        "memory_write",
        "review_create",
    ]


def test_invalid_model_plans_are_retried_but_never_rule_repaired() -> None:
    invalid = {
        "circle_id": "commons",
        "planet_id": "knowledge_librarian",
        "actions": [
            {
                "action": "calculate",
                "arguments": {"expression": "2+2"},
                "reason": "Invalid because this Planet lacks the Satellite.",
            }
        ],
        "reasoning_summary": "Deliberately unauthorized plan.",
    }
    model = ScriptedGemma([invalid, invalid])
    client = TestClient(
        create_app(gemma_client=model, chat_history=ConversationStore())
    )

    response = client.post(
        "/api/v2/wormhole/chat",
        json={"message": "Please work out two plus two."},
    )

    assert response.status_code == 502
    assert "valid authorized action plan" in response.json()["detail"]
    assert model.planning_calls == 2
    assert model.answer_calls == 0
