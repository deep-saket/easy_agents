from __future__ import annotations

from agents.collection_agent.nodes.plan_proposal_graph_node import PlanProposalGraphNode
from src.memory.types import WorkingMemory


def _execute(memory_state: dict, user_input: str = "continue") -> dict:
    memory = WorkingMemory(session_id="plan-objective-sync", state=memory_state)
    return PlanProposalGraphNode(llm=None, strict_llm_mode=False).execute(
        {"memory": memory, "user_input": user_input}
    )["conversation_plan"]


def _markers(plan: dict) -> dict[str, str]:
    markers = plan.get("step_markers") if isinstance(plan.get("step_markers"), dict) else {}
    return {
        str(key): str(value.get("state", "pending"))
        for key, value in markers.items()
        if isinstance(value, dict)
    }


def _nodes(plan: dict) -> dict[str, str]:
    return {
        str(node.get("id", "")): str(node.get("status", ""))
        for node in plan.get("nodes", [])
        if isinstance(node, dict)
    }


def test_discount_rejection_keeps_standard_options_active_without_false_confirmation() -> None:
    plan = _execute(
        {
            "active_case_id": "COLL-1002",
            "identity_verified": True,
            "right_party_status": "confirmed",
            "hardship_context": {"hardship_detected": True, "hardship_reason": "job_loss"},
            "discount_stage": "rejected",
            "discount_offered": True,
            "generic_options_offered_after_discount": False,
        },
        user_input="That discount is still not helpful.",
    )

    markers = _markers(plan)
    nodes = _nodes(plan)
    assert plan["current_node_id"] == "explain_dues"
    assert markers["discount_offer"] == "done"
    assert markers["confirmation"] == "pending"
    assert nodes["explain_dues"] == "in_progress"
    assert nodes["confirmation"] == "pending"


def test_promise_to_pay_followup_scheduled_marks_executed_objectives_done() -> None:
    plan = _execute(
        {
            "active_case_id": "COLL-1002",
            "identity_verified": True,
            "right_party_status": "confirmed",
            "payment_commitment_type": "PROMISE_TO_PAY",
            "promise_stage": "followup_scheduled",
            "promised_date": "5th",
            "promise_reference": "PTP-123",
            "promise_to_pay_details": {
                "promise_id": "PTP-123",
                "promised_date": "5th",
                "followup_schedule": {"schedule_id": "SCH-123"},
            },
        },
        user_input="5th will work for me",
    )

    markers = _markers(plan)
    nodes = _nodes(plan)
    assert plan["current_node_id"] == "confirmation"
    assert markers["collect_payment_intent"] == "done"
    assert markers["promise_date"] == "done"
    assert markers["promise_capture"] == "done"
    assert markers["promise_followup"] == "done"
    assert nodes["confirmation"] == "in_progress"


def test_full_payment_link_done_keeps_autopay_offer_active_until_declined_or_enabled() -> None:
    plan = _execute(
        {
            "active_case_id": "COLL-1002",
            "identity_verified": True,
            "right_party_status": "confirmed",
            "payment_commitment_type": "FULL_PAYMENT",
            "payment_resolution_stage": "confirmed",
            "full_payment_details": {
                "payment_reference_id": "PAY-123",
                "sms_confirmation": {"status": "sent"},
            },
            "autopay_response": "none",
            "autopay_stage": "",
        },
        user_input="Send me the link please",
    )

    markers = _markers(plan)
    nodes = _nodes(plan)
    assert plan["current_node_id"] == "autopay_offer"
    assert markers["collect_payment_intent"] == "done"
    assert markers["full_payment_options"] == "done"
    assert markers["full_payment_link"] == "done"
    assert markers["autopay_offer"] == "pending"
    assert nodes["autopay_offer"] == "in_progress"


def test_autopay_decline_marks_autopay_skipped_and_closes() -> None:
    plan = _execute(
        {
            "active_case_id": "COLL-1002",
            "identity_verified": True,
            "right_party_status": "confirmed",
            "payment_commitment_type": "FULL_PAYMENT",
            "payment_resolution_stage": "confirmed",
            "full_payment_details": {
                "payment_reference_id": "PAY-123",
                "sms_confirmation": {"status": "sent"},
            },
            "autopay_response": "declined",
        },
        user_input="Maybe later, thanks",
    )

    markers = _markers(plan)
    nodes = _nodes(plan)
    assert plan["current_node_id"] == "close_conversation"
    assert markers["autopay_offer"] == "skipped"
    assert nodes["close_conversation"] == "in_progress"


def test_human_transfer_branch_reflects_escalation_state() -> None:
    plan = _execute(
        {
            "active_case_id": "COLL-1002",
            "identity_verified": True,
            "right_party_status": "confirmed",
            "hardship_context": {"hardship_detected": True, "hardship_reason": "job_loss"},
            "discount_stage": "rejected",
            "discount_offered": True,
            "generic_options_offered_after_discount": True,
            "human_escalation_status": "queued",
            "human_transfer_status": "pending",
        },
        user_input="None of these options work.",
    )

    markers = _markers(plan)
    nodes = _nodes(plan)
    assert plan["current_node_id"] == "transfer_to_specialist"
    assert markers["human_escalation"] == "done"
    assert markers["confirmation"] == "skipped"
    assert nodes["transfer_to_specialist"] == "in_progress"


def test_partial_payment_projection_uses_tool_backed_runtime_evidence() -> None:
    plan = _execute(
        {
            "active_case_id": "COLL-1002",
            "identity_verified": True,
            "right_party_status": "confirmed",
            "payment_commitment_type": "PARTIAL_PAYMENT",
            "partial_payment_stage": "confirmed",
            "partial_payment_details": {
                "partial_payment_amount": 8000.0,
                "payment_reference_id": "PAY-8000",
                "sms_confirmation": {"status": "sent"},
            },
        },
        user_input="I received the link",
    )

    markers = _markers(plan)
    nodes = _nodes(plan)
    assert plan["current_node_id"] == "confirmation"
    assert markers["collect_payment_intent"] == "done"
    assert markers["partial_amount"] == "done"
    assert markers["partial_link"] == "done"
    assert nodes["confirmation"] == "in_progress"
    assert sum(status == "in_progress" for status in nodes.values()) == 1


def test_discount_selected_without_hold_skips_unexecuted_hold_assessment() -> None:
    plan = _execute(
        {
            "active_case_id": "COLL-1002",
            "identity_verified": True,
            "right_party_status": "confirmed",
            "hardship_context": {"hardship_detected": True, "hardship_reason": "job_loss"},
            "discount_stage": "offered",
            "discount_offered": True,
            "hardship_hold_stage": "",
            "hold_response": "none",
        },
        user_input="Do you have a discount option?",
    )

    markers = _markers(plan)
    nodes = _nodes(plan)
    assert plan["current_node_id"] == "discount_offer"
    assert markers["assess_after_hold"] == "skipped"
    assert nodes["discount_offer"] == "in_progress"
    assert sum(status == "in_progress" for status in nodes.values()) == 1


def test_runtime_objective_switch_leaves_no_stale_active_payment_node() -> None:
    initial = {
        "active_case_id": "COLL-1002",
        "identity_verified": True,
        "right_party_status": "confirmed",
        "payment_commitment_type": "FULL_PAYMENT",
        "payment_resolution_stage": "options_offered",
    }
    first_plan = _execute(initial, user_input="I can pay now")
    switched = dict(initial)
    switched.update(
        {
            "active_conversation_plan": first_plan,
            "payment_commitment_type": "NONE",
            "payment_resolution_stage": "",
            "customer_payment_posture": "cannot_pay",
            "hardship_context": {"hardship_detected": True, "hardship_reason": "job_loss"},
        }
    )

    plan = _execute(switched, user_input="I lost my job and cannot pay now")
    nodes = _nodes(plan)
    assert plan["current_node_id"] == "evaluate_assistance"
    assert nodes["evaluate_assistance"] == "in_progress"
    assert nodes["full_payment_options"] != "in_progress"
    assert sum(status == "in_progress" for status in nodes.values()) == 1
