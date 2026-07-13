from __future__ import annotations

import json
from pathlib import Path

from agents.collection_agent.nodes.collection_react_node import CollectionReactNode
from agents.collection_agent.nodes.collection_response_node import CollectionResponseNode
from agents.collection_agent.nodes.negotiation_classification_node import NegotiationClassificationNode
from agents.collection_agent.nodes.plan_proposal_directive_node import PlanProposalDirectiveNode
from agents.collection_agent.nodes.plan_proposal_graph_node import PlanProposalGraphNode
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.followup_schedule_tool import FollowupScheduleTool
from agents.collection_agent.tools.promise_capture_tool import PromiseCaptureTool
from src.memory.types import WorkingMemory
from src.nodes.tool_execution_node import ToolExecutionNode
from src.tools.executor import ToolExecutor
from src.tools.registry import ToolRegistry


def _store(tmp_path: Path) -> CollectionDataStore:
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "customers.json").write_text(
        json.dumps(
            [{
                "customer_id": "CUST-2002",
                "phone": "+919900001002",
                "email": "rohan.gupta@example.com",
            }]
        ),
        encoding="utf-8",
    )
    return CollectionDataStore(base_dir=tmp_path)


def _memory() -> WorkingMemory:
    return WorkingMemory(
        session_id="promise-to-pay-flow",
        state={
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "active_customer_name": "Rohan Gupta",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
            "right_party_status": "confirmed",
            "conversation_mode": "collections",
            "active_collection_context": {
                "case": {
                    "case_id": "COLL-1002",
                    "loan_id": "LOAN-3002",
                    "overdue_amount": 37800.0,
                },
                "policy": {
                    "allow_partial_payment": True,
                    "min_partial_payment_pct": 20,
                    "max_promise_days": 60,
                },
                "customer": {
                    "variables": {
                        "[CUSTOMER_NAME]": "Rohan Gupta",
                        "[POLICY_NUMBER]": "LOAN-3002",
                        "[AMOUNT]": "37800.00",
                        "[DUE_DATE]": "2026-06-10",
                    }
                },
            },
        },
    )


def _registry(store: CollectionDataStore) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(PromiseCaptureTool(store=store))
    registry.register(FollowupScheduleTool(store=store))
    return registry


def test_ptp_intent_without_specific_date_requests_date() -> None:
    memory = _memory()
    node = NegotiationClassificationNode(llm=None, strict_llm_mode=False)

    update = node.execute(
        {
            "user_input": "I get paid at the end of the month. I can pay it then, just not right now.",
            "memory": memory,
            "extracted_entities_turn": {},
            "identity_verified": True,
            "verification_missing_fields": [],
            "verification_verified_fields": ["dob", "phone"],
        }
    )

    assert update["payment_commitment_type"] == "PROMISE_TO_PAY"
    assert update["promise_stage"] == "date_required"
    assert memory.state["promised_date"] == ""


def test_ptp_initial_timing_does_not_promote_extracted_date() -> None:
    memory = _memory()
    node = NegotiationClassificationNode(llm=None, strict_llm_mode=False)

    update = node.execute(
        {
            "user_input": "I get paid at the end of the month. I can pay it then, just not right now.",
            "memory": memory,
            "extracted_entities_turn": {"promised_date": "end of the month"},
            "identity_verified": True,
            "verification_missing_fields": [],
            "verification_verified_fields": ["dob", "phone"],
        }
    )

    assert update["payment_commitment_type"] == "PROMISE_TO_PAY"
    assert update["promise_stage"] == "date_required"
    assert update["promised_date"] == ""
    assert memory.state["promised_date"] == ""


def test_ptp_extracted_date_promotes_to_date_captured() -> None:
    memory = _memory()
    memory.set_state(
        payment_commitment_type="PROMISE_TO_PAY",
        customer_payment_posture="promise_to_pay",
        conversation_mode="promise_capture",
        promise_stage="date_required",
        promised_date="",
    )
    node = NegotiationClassificationNode(llm=None, strict_llm_mode=False)

    update = node.execute(
        {
            "user_input": "4th would work for me",
            "memory": memory,
            "extracted_entities_turn": {"promised_date": "2026-07-04"},
            "identity_verified": True,
            "verification_missing_fields": [],
            "verification_verified_fields": ["dob", "phone"],
        }
    )

    assert update["payment_commitment_type"] == "PROMISE_TO_PAY"
    assert update["promised_date"] == "2026-07-04"
    assert update["promise_stage"] == "date_captured"
    assert memory.state["promised_date"] == "2026-07-04"
    assert memory.state["promise_stage"] == "date_captured"


def test_ptp_date_reply_uses_latest_customer_text_before_stale_extracted_date() -> None:
    memory = _memory()
    memory.set_state(
        payment_commitment_type="PROMISE_TO_PAY",
        customer_payment_posture="promise_to_pay",
        promise_stage="date_required",
        promised_date="",
    )
    node = NegotiationClassificationNode(llm=None, strict_llm_mode=False)

    update = node.execute(
        {
            "user_input": "5th will work for me",
            "memory": memory,
            "extracted_entities_turn": {"promised_date": "2024-08-05"},
            "identity_verified": True,
            "verification_missing_fields": [],
            "verification_verified_fields": ["dob", "phone"],
        }
    )

    assert update["payment_commitment_type"] == "PROMISE_TO_PAY"
    assert update["promised_date"] == "5th"
    assert update["promise_stage"] == "date_captured"
    assert memory.state["promised_date"] == "5th"


def test_ptp_date_reply_preserves_waiting_state_from_memory() -> None:
    memory = _memory()
    memory.set_state(
        payment_commitment_type="PROMISE_TO_PAY",
        customer_payment_posture="promise_to_pay",
        promise_stage="date_required",
        promised_date="",
    )
    node = NegotiationClassificationNode(llm=None, strict_llm_mode=False)

    update = node.execute(
        {
            "user_input": "30th july would work for me",
            "memory": memory,
            "extracted_entities_turn": {},
            "identity_verified": True,
            "verification_missing_fields": [],
            "verification_verified_fields": ["dob", "phone"],
        }
    )

    assert update["payment_commitment_type"] == "PROMISE_TO_PAY"
    assert update["promised_date"] == "30th july"
    assert update["promise_stage"] == "date_captured"


def test_ptp_thanks_after_followup_scheduled_does_not_reopen_date_request() -> None:
    memory = _memory()
    memory.set_state(
        payment_commitment_type="PROMISE_TO_PAY",
        customer_payment_posture="promise_to_pay",
        conversation_mode="promise_capture",
        active_dialogue_owner="promise_capture",
        promise_stage="followup_scheduled",
        promised_date="5th",
        promise_reference="PTP-ABC123",
        final_disposition="PROMISE_TO_PAY_SCHEDULED",
        promise_date_rejection_reason="promised_date_exceeds_5_days",
    )
    node = NegotiationClassificationNode(llm=None, strict_llm_mode=False)

    update = node.execute(
        {
            "user_input": "sure thankyou",
            "memory": memory,
            "extracted_entities_turn": {},
            "identity_verified": True,
            "verification_missing_fields": [],
            "verification_verified_fields": ["dob", "phone"],
        }
    )

    assert update["payment_commitment_type"] == "PROMISE_TO_PAY"
    assert update["promised_date"] == "5th"
    assert update["promise_stage"] == "followup_scheduled"


def test_verification_details_do_not_trigger_ptp() -> None:
    memory = _memory()
    node = NegotiationClassificationNode(llm=None, strict_llm_mode=False)

    update = node.execute(
        {
            "user_input": "My phone number is : 9900001002 and date of birth is 1988-04-22",
            "memory": memory,
            "extracted_entities_turn": {},
            "identity_verified": True,
            "verification_missing_fields": [],
            "verification_verified_fields": ["dob", "phone"],
        }
    )

    assert update["payment_commitment_type"] == "NONE"
    assert update["promise_stage"] == ""
    assert update["promised_date"] == ""


def test_ptp_specific_date_records_promise_and_schedules_followup(tmp_path: Path) -> None:
    store = _store(tmp_path)
    registry = _registry(store)
    memory = _memory()
    memory.set_state(
        payment_commitment_type="PROMISE_TO_PAY",
        customer_payment_posture="promise_to_pay",
        conversation_mode="promise_capture",
        promise_stage="date_captured",
        promised_date="the 30th",
    )
    react = CollectionReactNode(tool_registry=registry)
    executor = ToolExecutionNode(executor=ToolExecutor(registry=registry))

    first = react.execute({"memory": memory, "steps": 0, "observations": []})
    assert first["decision"].tool_call.tool_name == "promise_capture"
    first_tool = executor.execute({"memory": memory, "decision": first["decision"], "steps": 0})

    second = react.execute(
        {
            "memory": memory,
            "steps": 1,
            "observations": [first_tool["observation"]],
        }
    )
    assert second["decision"].tool_call.tool_name == "followup_schedule"
    second_tool = executor.execute({"memory": memory, "decision": second["decision"], "steps": 1})

    final = react.execute(
        {
            "memory": memory,
            "steps": 1,
            "observations": [first_tool["observation"], second_tool["observation"]],
        }
    )

    assert final["decision"].done is True
    assert memory.state["promise_stage"] == "followup_scheduled"
    assert memory.state["promise_reference"].startswith("PTP-")
    assert memory.state["final_disposition"] == "PROMISE_TO_PAY_SCHEDULED"
    assert json.loads((tmp_path / "runtime" / "promises.json").read_text(encoding="utf-8"))
    assert json.loads((tmp_path / "runtime" / "followups.json").read_text(encoding="utf-8"))


def test_ptp_rejects_date_outside_policy_window(tmp_path: Path) -> None:
    store = _store(tmp_path)
    registry = _registry(store)
    memory = _memory()
    memory.state["active_collection_context"]["policy"]["max_promise_days"] = 5
    memory.set_state(
        payment_commitment_type="PROMISE_TO_PAY",
        customer_payment_posture="promise_to_pay",
        conversation_mode="promise_capture",
        promise_stage="date_captured",
        promised_date="2099-01-01",
    )

    update = CollectionReactNode(tool_registry=registry).execute(
        {"memory": memory, "steps": 0, "observations": []}
    )

    assert update["decision"].tool_call is None
    assert "outside the allowed payment-commitment window of 5 days" in update["decision"].response_text
    assert "What earlier date would work" in update["decision"].response_text
    assert memory.state["promise_stage"] == "date_invalid"
    assert memory.state["promise_date_rejection_reason"].startswith("promised_date_exceeds")


def test_ptp_confirmation_and_plan_tree_close_by_name() -> None:
    memory = _memory()
    memory.set_state(
        payment_commitment_type="PROMISE_TO_PAY",
        customer_payment_posture="promise_to_pay",
        conversation_mode="promise_capture",
        promise_stage="followup_scheduled",
        promised_date="the 30th",
        promise_reference="PTP-ABC123",
        promise_to_pay_details={
            "promise_id": "PTP-ABC123",
            "promised_date": "the 30th",
            "followup_schedule": {"schedule_id": "SCH-ABC123"},
        },
    )
    graph = PlanProposalGraphNode()
    initial = graph.execute({"memory": memory, "user_input": "The 30th would work."})
    memory.set_state(active_conversation_plan=initial["conversation_plan"])
    directive = PlanProposalDirectiveNode().execute({"memory": memory})
    response = CollectionResponseNode(strict_llm_mode=False).execute(
        {
            "memory": memory,
            "plan_proposal": directive["plan_proposal"],
            "response_target": "customer",
        }
    )

    assert "PTP-ABC123" in response["response"]
    assert "secure payment link a day before" in response["response"]
    assert memory.state["promise_stage"] == "confirmed"
    plan = response["conversation_plan"]
    assert plan["current_node_id"] == "close_conversation"
    markers = plan["step_markers"]
    assert markers["promise_capture"]["state"] == "done"
    assert markers["promise_followup"]["state"] == "done"

    closing = PlanProposalDirectiveNode().execute({"memory": memory})
    close_response = CollectionResponseNode(strict_llm_mode=False).execute(
        {
            "memory": memory,
            "plan_proposal": closing["plan_proposal"],
            "response_target": "customer",
        }
    )
    assert "Rohan Gupta" in close_response["response"]
    assert "goodbye" in close_response["response"].lower()
