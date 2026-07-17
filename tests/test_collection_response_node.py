from __future__ import annotations

from agents.collection_agent.nodes.collection_response_node import CollectionResponseNode
from agents.collection_agent.nodes.plan_proposal_graph_node import PlanProposalGraphNode
from agents.collection_agent.utils.plan_proposal_utils import finalize_conversation_memory
from src.memory.types import WorkingMemory


def _build_node() -> CollectionResponseNode:
    return CollectionResponseNode(
        llm=None,
        strict_llm_mode=False,
    )


class _FailingRenderLLM:
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        raise RuntimeError("LLM renderer failed.")


class _ScriptedRenderLLM:
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        return {
            "message": "I can talk through a practical arrangement based on what works for you.",
            "response_target": "customer",
        }


class _FullPaymentNaturalLLM:
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        assert "Verified response context JSON" in user_prompt
        return {
            "message": (
                "The payment link is on its way to your registered mobile. "
                "Your reference number is PAY-123. Once payment is received, you will get an instant receipt. "
                "Would you like to set up auto-pay so future installments are not missed?"
            ),
            "response_target": "customer",
        }


class _HallucinatedReferenceLLM:
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        return {
            "message": "The link is on its way, and your reference number is PAY-FAKE999.",
            "response_target": "customer",
        }


class _IncompleteCallbackLLM:
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        return {
            "message": "I have scheduled your callback for 5 PM. EasySecure Financial Services will be in touch then. Have a great day.",
            "response_target": "customer",
        }


class _UnsupportedArrangementLLM:
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        return {
            "message": (
                "I understand you're looking for more flexibility. We can arrange a payment plan "
                "where you pay the revised amount of 34020.00 in smaller installments over the next few months. "
                "Would splitting the payment make it easier for you to manage?"
            ),
            "response_target": "customer",
        }


class _CallbackRequestContextLLM:
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        assert "+91-1800-555-2002" not in user_prompt
        assert "EasySecure Financial Services" in user_prompt
        return {
            "message": "I understand you're in a meeting. When would be a suitable time for us to call you back?",
            "response_target": "customer",
        }


def test_response_node_uses_llm_first_for_full_payment_objective() -> None:
    node = CollectionResponseNode(
        llm=_FullPaymentNaturalLLM(),
        strict_llm_mode=True,
        system_prompt="render",
        render_user_prompt="Verified response context JSON: {verified_response_context_json}",
    )
    memory = WorkingMemory(
        session_id="response-full-payment",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
            "payment_commitment_type": "FULL_PAYMENT",
            "payment_resolution_stage": "confirmed",
            "full_payment_details": {
                "payment_reference_id": "PAY-123",
                "sms_confirmation": {"status": "sent"},
            },
        },
    )

    update = node.execute(
        {
            "user_input": "Send me the link, please.",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "full_payment_confirmation",
                    "dialogue_action": "confirm_full_payment_link",
                    "response_mode": "informational",
                },
            },
        }
    )

    assert update["response_render_debug"]["renderer_fallback_used"] is False
    assert "reference number is PAY-123" in update["response"]
    assert "auto-pay" in update["response"]


def test_response_node_falls_back_when_llm_fails_for_full_payment_objective() -> None:
    node = CollectionResponseNode(
        llm=_FailingRenderLLM(),
        strict_llm_mode=True,
        system_prompt="render",
        render_user_prompt="Verified response context JSON: {verified_response_context_json}",
    )
    memory = WorkingMemory(
        session_id="response-full-payment-fallback",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
            "payment_commitment_type": "FULL_PAYMENT",
            "payment_resolution_stage": "confirmed",
            "full_payment_details": {
                "payment_reference_id": "PAY-123",
                "sms_confirmation": {"status": "sent"},
            },
        },
    )

    update = node.execute(
        {
            "user_input": "Send me the link, please.",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "full_payment_confirmation",
                    "dialogue_action": "confirm_full_payment_link",
                    "response_mode": "informational",
                },
            },
        }
    )

    assert update["response_render_debug"]["renderer_fallback_used"] is True
    assert "reference number is PAY-123" in update["response"]


def test_response_node_falls_back_when_llm_invents_reference() -> None:
    node = CollectionResponseNode(
        llm=_HallucinatedReferenceLLM(),
        strict_llm_mode=True,
        system_prompt="render",
        render_user_prompt="Verified response context JSON: {verified_response_context_json}",
    )
    memory = WorkingMemory(
        session_id="response-full-payment-hallucinated-reference",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
            "payment_commitment_type": "FULL_PAYMENT",
            "payment_resolution_stage": "confirmed",
            "full_payment_details": {
                "payment_reference_id": "PAY-123",
                "sms_confirmation": {"status": "sent"},
            },
        },
    )

    update = node.execute(
        {
            "user_input": "Send me the link, please.",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "full_payment_confirmation",
                    "dialogue_action": "confirm_full_payment_link",
                    "response_mode": "informational",
                },
            },
        }
    )

    assert update["response_render_debug"]["renderer_fallback_used"] is True
    assert "PAY-FAKE999" not in update["response"]
    assert "PAY-123" in update["response"]


def test_response_node_explains_below_minimum_partial_payment_validation() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-partial-validation",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
            "partial_payment_stage": "collecting_amount",
            "partial_payment_validation": {
                "status": "rejected",
                "reason": "below_minimum_partial_payment",
                "offered_amount": 7000.0,
                "offered_pct": 18.52,
                "minimum_partial_payment_pct": 20.0,
                "minimum_partial_payment_amount": 7560.0,
                "total_due": 37800.0,
            },
        },
    )

    update = node.execute(
        {
            "user_input": "I can pay 7000 today.",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "partial_payment_amount_request",
                    "dialogue_action": "ask_partial_payment_amount",
                    "response_mode": "empathetic",
                },
            },
        }
    )

    assert "7000.00" in update["response"]
    assert "7560.00" in update["response"]
    assert "20%" in update["response"]
    assert "How much do you think" not in update["response"]


def test_response_node_allows_llm_for_arrangement_reasoning() -> None:
    node = CollectionResponseNode(
        llm=_ScriptedRenderLLM(),
        strict_llm_mode=True,
        system_prompt="render",
        render_user_prompt="{template_id}",
    )
    memory = WorkingMemory(
        session_id="response-arrangement",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
        },
    )

    update = node.execute(
        {
            "user_input": "Can we discuss another option?",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "present_arrangement_options",
                    "dialogue_action": "discuss_arrangement",
                    "response_mode": "negotiation",
                },
            },
        }
    )

    assert update["response"] == "I can talk through a practical arrangement based on what works for you."
    assert update["response_render_debug"]["renderer_fallback_used"] is False


def test_response_node_blocks_unsupported_arrangement_split_after_discount() -> None:
    node = CollectionResponseNode(
        llm=_UnsupportedArrangementLLM(),
        strict_llm_mode=True,
        system_prompt="render",
        render_user_prompt="Verified response context JSON: {verified_response_context_json}",
    )
    memory = WorkingMemory(
        session_id="response-arrangement-unsupported-split",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
            "generic_options_offered_after_discount": True,
            "active_collection_context": {
                "policy": {
                    "allow_partial_payment": True,
                    "min_partial_payment_pct": 20,
                    "max_promise_days": 5,
                    "restructure_allowed": True,
                }
            },
        },
    )

    update = node.execute(
        {
            "user_input": "do you have some more options?",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "present_arrangement_options",
                    "dialogue_action": "present_offer",
                    "response_mode": "negotiation",
                },
            },
        }
    )

    response = update["response"].lower()
    assert update["response_render_debug"]["renderer_fallback_used"] is True
    assert "smaller installments" not in response
    assert "splitting the payment" not in response
    assert "partial payment starting from 20%" in response
    assert "payment commitment within 5 days" in response
    assert "standard restructure review" in response


def test_response_node_uses_graph_objective_for_customer_callback_over_stale_verification() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-customer-callback",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "identity_verified": False,
            "right_party_status": "awaiting_confirmation",
            "customer_callback_stage": "awaiting_callback",
            "active_dialogue_owner": "customer_callback",
        },
    )

    update = node.execute(
        {
            "user_input": "Yes, but I'm in a meeting right now",
            "memory": memory,
            "conversation_plan": {
                "current_node_id": "customer_callback",
                "step_markers": {
                    "verify_identity": {
                        "state": "skipped",
                        "reason": "customer_requested_callback_before_verification",
                    },
                    "customer_callback": {"state": "pending"},
                },
            },
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "collect_verification",
                    "dialogue_action": "ask_verification",
                    "response_mode": "compliance",
                },
            },
        }
    )

    lowered = update["response"].lower()
    assert "callback" in lowered
    assert "date of birth" not in lowered
    assert "phone number" not in lowered
    assert update["response_render_debug"]["template_selected"] == "customer_callback_request"


def test_response_node_customer_callback_request_does_not_expose_contact_number_to_llm() -> None:
    node = CollectionResponseNode(
        llm=_CallbackRequestContextLLM(),
        strict_llm_mode=True,
        system_prompt="render",
        render_user_prompt="Verified response context JSON: {verified_response_context_json}",
    )
    memory = WorkingMemory(
        session_id="response-customer-callback-no-contact",
        state={
            "active_customer_name": "Rohan Gupta",
            "identity_verified": False,
            "customer_callback_stage": "awaiting_callback",
            "active_collection_context": {
                "customer": {
                    "variables": {
                        "[COMPANY_NAME]": "EasySecure Financial Services",
                        "[CONTACT_NUMBER]": "+91-1800-555-2002",
                    }
                }
            },
        },
    )

    update = node.execute(
        {
            "user_input": "Yes, but I'm in a meeting right now",
            "memory": memory,
            "conversation_plan": {"current_node_id": "customer_callback"},
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "customer_callback_request",
                    "dialogue_action": "customer_callback_request",
                    "response_mode": "empathetic",
                },
            },
        }
    )

    assert "+91-1800-555-2002" not in update["response"]
    assert update["response_render_debug"]["renderer_fallback_used"] is False


def test_response_node_customer_callback_confirmation_includes_reference_and_safe_purpose() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-customer-callback-confirmed",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "active_company_name": "EasySecure Financial Services",
            "identity_verified": False,
            "customer_callback_stage": "completed",
            "customer_callback_time": "at 5 PM today",
            "outbound_callback_status": "scheduled",
            "outbound_callback_job_id": "CALL-123",
        },
    )

    update = node.execute(
        {
            "user_input": "Can you call me this evening, around 5 PM?",
            "memory": memory,
            "conversation_plan": {"current_node_id": "customer_callback"},
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "customer_callback_confirmation",
                    "dialogue_action": "customer_callback_confirmation",
                    "response_mode": "empathetic",
                },
            },
        }
    )

    response = update["response"]
    assert "5 PM" in response
    assert "premium installment on your policy" in response
    assert "CALL-123" in response
    assert "Rohan Gupta" in response
    assert "date of birth" not in response.lower()


def test_response_node_callback_llm_missing_reference_falls_back_to_complete_template() -> None:
    node = CollectionResponseNode(
        llm=_IncompleteCallbackLLM(),
        strict_llm_mode=True,
        system_prompt="render",
        render_user_prompt="Verified response context JSON: {verified_response_context_json}",
    )
    memory = WorkingMemory(
        session_id="response-customer-callback-llm-fallback",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "identity_verified": False,
            "customer_callback_stage": "completed",
            "customer_callback_time": "at 5 PM today",
            "outbound_callback_status": "scheduled",
            "outbound_callback_job_id": "CALL-123",
        },
    )

    update = node.execute(
        {
            "user_input": "Can you call me this evening, around 5 PM?",
            "memory": memory,
            "conversation_plan": {"current_node_id": "customer_callback"},
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "customer_callback_confirmation",
                    "dialogue_action": "customer_callback_confirmation",
                    "response_mode": "empathetic",
                },
            },
        }
    )

    assert update["response_render_debug"]["renderer_fallback_used"] is True
    assert "CALL-123" in update["response"]
    assert "premium installment on your policy" in update["response"]


def test_response_node_uses_callback_confirmation_after_graph_advances_to_close() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-customer-callback-close-node",
        state={
            "active_customer_name": "Aditi Sharma",
            "identity_verified": False,
            "customer_callback_stage": "completed",
            "customer_callback_time": "at 3 PM",
            "outbound_callback_status": "scheduled",
            "outbound_callback_job_id": "CALL-456",
        },
    )

    update = node.execute(
        {
            "user_input": "Can you call me this evening, around 3 PM?",
            "memory": memory,
            "conversation_plan": {"current_node_id": "close_conversation"},
            "observation": {
                "tool_name": "outbound_callback_schedule",
                "output": {"status": "scheduled", "job_id": "CALL-456"},
            },
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "close_conversation",
                    "dialogue_action": "close_conversation",
                },
            },
        }
    )

    assert update["response_render_debug"]["template_selected"] == "customer_callback_confirmation"
    assert "CALL-456" in update["response"]
    assert "premium installment on your policy" in update["response"]
    assert "Aditi Sharma" in update["response"]


def test_response_node_generic_closing_uses_customer_name() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-generic-close",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "identity_verified": True,
        },
    )

    update = node.execute(
        {
            "user_input": "No, thanks",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "close_conversation",
                    "dialogue_action": "close_conversation",
                    "response_mode": "informational",
                },
            },
        }
    )

    assert "Thank you for your time, Rohan Gupta." in update["response"]


def test_response_node_renders_from_hardship_response_directive() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-hardship",
        state={
            "active_customer_name": "Aditi",
            "active_case_id": "COLL-1001",
            "active_overdue_amount": 1200.0,
            "conversation_mode": "hardship_negotiation",
            "negotiation_stage": "assessing_capacity",
            "customer_payment_posture": "cannot_pay",
            "hardship_context": {
                "hardship_detected": True,
                "hardship_reason": "job_loss",
                "confidence": 0.96,
            },
            "response_mode": "empathetic",
            "active_dialogue_owner": "plan_proposal",
            "identity_verified": True,
            "active_collection_context": {
                "policy": {
                    "allow_partial_payment": True,
                    "min_partial_payment_pct": 20,
                    "max_promise_days": 5,
                    "restructure_allowed": True,
                }
            },
        },
    )
    state = {
        "user_input": "I lost my job",
        "memory": memory,
        "plan_proposal": {
            "target": "customer",
            "intent": "generic_plan",
            "response_directive": {
                "conversation_objective": "assess_affordability",
                "dialogue_action": "ask_affordable_amount",
                "response_mode": "empathetic",
                "required_response_elements": [
                    "acknowledge_hardship",
                    "explain_applicable_policy_options",
                    "ask_affordable_amount",
                ],
                "forbidden_dialogue_actions": ["restart_collections_menu", "ask_pay_now_or_arrangement"],
                "allowed_dialogue_actions": ["acknowledge_hardship", "ask_affordable_amount"],
                "customer_facing_goal": "Ask the customer what monthly amount is manageable.",
                "handoff_target": None,
            },
        },
    }

    update = node.execute(state)
    response = update["response"]

    lowered = response.lower()
    assert "pay now" not in lowered
    assert "schedule a follow-up" not in lowered
    assert "partial payment starting from 20%" in lowered
    assert "payment commitment within 5 days" in lowered
    assert "standard restructure review" in lowered
    assert "what amount or payment date" in lowered
    assert update["response_render_debug"]["template_selected"] == "capacity_question"
    assert update["response_render_debug"]["response_mode"] == "empathetic"
    assert update["response_render_debug"]["renderer_fallback_used"] is True


def test_response_node_renders_staged_job_loss_hold_flow_from_data() -> None:
    node = _build_node()
    base_state = {
        "active_customer_name": "Rohan Gupta",
        "active_case_id": "COLL-1002",
        "active_overdue_amount": 37800.0,
        "identity_verified": True,
        "active_collection_context": {
            "customer": {
                "variables": {
                    "[POLICY_NUMBER]": "LOAN-3002",
                    "[AMOUNT]": "37800.00",
                    "[DUE_DATE]": "2026-06-10",
                    "[REF_NUMBER]": "COLL-1002",
                }
            },
            "case": {"loan_id": "LOAN-3002"},
        },
    }
    memory = WorkingMemory(session_id="response-hold", state=dict(base_state))

    purpose = node.execute(
        {
            "user_input": "verified",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "purpose_disclosure",
                    "dialogue_action": "disclose_call_purpose",
                    "response_mode": "informational",
                },
            },
        }
    )["response"]
    assert "policy LOAN-3002" in purpose
    assert "37800.00" in purpose
    assert "2026-06-10" in purpose
    assert "20%" not in purpose
    assert "5 days" not in purpose

    memory.set_state(
        hardship_hold_program={
            "max_hold_months": 2,
            "benefits_remain_active": True,
            "confirmation_sla_hours": 24,
        }
    )
    offer = node.execute(
        {
            "user_input": "I lost my job",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "hardship_hold_offer",
                    "dialogue_action": "offer_hardship_hold",
                    "response_mode": "empathetic",
                },
            },
        }
    )["response"]
    assert "hold for up to 2 months" in offer
    assert "no impact to your policy benefits" in offer
    assert "20%" not in offer

    memory.set_state(
        hardship_hold_stage="confirmed",
        active_conversation_plan={
            "plan_id": "PLAN-HOLD-1",
            "version": 1,
            "status": "active",
            "mode": "hardship_negotiation",
            "objective": "Resolve hardship",
            "root_node_id": "open_and_context",
            "current_node_id": "confirmation",
            "previous_node_id": "resolution_offer",
            "next_node_ids": ["close_conversation"],
            "nodes": [
                {"id": "confirmation", "label": "Confirm agreed outcome and reference", "status": "in_progress"},
                {"id": "close_conversation", "label": "Close conversation", "status": "pending"},
            ],
            "edges": [
                {"from": "confirmation", "to": "close_conversation", "condition": "outcome_confirmed"},
            ],
            "step_markers": {
                "confirmation": {"state": "pending"},
                "close_conversation": {"state": "pending"},
            },
            "timeline": [],
            "timeline_snapshots": [],
        },
        hardship_hold_details={
            "hold_months": 2,
            "reference_number": "HOLD-A1B2C3D4E5",
            "confirmation_sla_hours": 24,
            "sms_confirmation": {"status": "sent"},
            "email_confirmation": {"status": "sent"},
        }
    )
    confirmation_update = node.execute(
        {
            "user_input": "Yes, that would really help",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "hardship_hold_confirmation",
                    "dialogue_action": "confirm_hardship_hold",
                    "response_mode": "empathetic",
                },
            },
        }
    )
    confirmation = confirmation_update["response"]
    assert "2-month hold" in confirmation
    assert "reference number is HOLD-A1B2C3D4E5" in confirmation
    assert "confirmation has been sent by sms and email" in confirmation.lower()
    assert "anything else" not in confirmation.lower()
    assert "conversation_plan" not in confirmation_update
    assert "hardship_hold_confirmation" in memory.state["completed_objectives"]
    advanced_plan = PlanProposalGraphNode(llm=None, strict_llm_mode=False).execute(
        {"memory": memory, "user_input": "continue"}
    )["conversation_plan"]
    advanced_nodes = {item["id"]: item for item in advanced_plan["nodes"]}
    assert advanced_plan["current_node_id"] == "close_conversation"
    assert advanced_plan["status"] == "active"
    assert advanced_plan["step_markers"]["confirmation"]["state"] == "done"
    assert advanced_nodes["confirmation"]["status"] == "done"
    assert advanced_nodes["close_conversation"]["status"] == "in_progress"
    assert advanced_plan["timeline_snapshots"][-1]["update"]["operation"] == "runtime_projection"

    closing_update = node.execute(
        {
            "user_input": "No, thank you",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "hardship_hold_closing",
                    "dialogue_action": "close_hardship_hold_conversation",
                    "response_mode": "empathetic",
                },
            },
        }
    )
    assert "Thank you for your time, Rohan Gupta." in closing_update["response"]
    assert closing_update["response"].endswith("Goodbye.")
    assert closing_update["conversation_closing"] is True
    assert closing_update["termination_grace_seconds"] == 3.0

    finalize_conversation_memory(memory)
    completed_plan = memory.state["active_conversation_plan"]
    completed_nodes = {item["id"]: item for item in completed_plan["nodes"]}
    assert completed_plan["status"] == "completed"
    assert completed_plan["step_markers"]["confirmation"]["state"] == "done"
    assert completed_plan["step_markers"]["close_conversation"]["state"] == "done"
    assert completed_nodes["confirmation"]["status"] == "done"
    assert completed_nodes["close_conversation"]["status"] == "done"


def test_response_node_opens_with_dynamic_right_party_confirmation() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-verification",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "active_overdue_amount": 1200.0,
            "turn_index": 0,
            "greeted": False,
            "conversation_mode": "verification",
            "negotiation_stage": "none",
            "customer_payment_posture": "unknown",
            "hardship_context": {
                "hardship_detected": False,
                "hardship_reason": None,
                "confidence": 0.0,
            },
            "response_mode": "compliance",
            "active_dialogue_owner": "verification",
            "identity_verified": False,
            "active_verification_required_fields": ["dob", "phone"],
            "verification_missing_fields": ["dob", "phone"],
            "verification_entities": {},
            "active_collection_context": {
                "customer": {
                    "variables": {
                        "[AGENT_NAME]": "Alex",
                        "[COMPANY_NAME]": "EasySecure Financial Services",
                    }
                },
                "case": {"assigned_agent": "Fallback Agent"},
            },
        },
    )
    state = {
        "user_input": "hello",
        "memory": memory,
        "plan_proposal": {
            "target": "customer",
            "intent": "generic_plan",
        },
    }

    response = node.execute(state)["response"].lower()

    assert "alex" in response
    assert "easysecure financial services" in response
    assert "may be recorded for quality and training" in response
    assert "may i please speak with rohan gupta" in response
    assert "overdue amount" not in response
    assert "date of birth" not in response
    assert "registered phone number" not in response


def test_response_node_requests_verification_after_opening() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-verification-followup",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "active_overdue_amount": 1200.0,
            "turn_index": 1,
            "greeted": True,
            "conversation_mode": "verification",
            "negotiation_stage": "none",
            "customer_payment_posture": "unknown",
            "hardship_context": {
                "hardship_detected": False,
                "hardship_reason": None,
                "confidence": 0.0,
            },
            "response_mode": "compliance",
            "active_dialogue_owner": "verification",
            "identity_verified": False,
            "active_verification_required_fields": ["dob", "phone"],
            "verification_missing_fields": ["dob", "phone"],
            "verification_entities": {},
        },
    )
    state = {
        "user_input": "Yes, that's me.",
        "memory": memory,
        "plan_proposal": {
            "target": "customer",
            "intent": "generic_plan",
        },
    }

    response = node.execute(state)["response"].lower()

    assert "privacy and security" in response
    assert "before i share any account details" in response
    assert "date of birth" in response
    assert "registered phone number" in response
    assert "overdue amount" not in response


def test_response_node_wrong_party_privacy_notice_is_separate_from_callback_request() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-wrong-party",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "active_overdue_amount": 37800.0,
            "identity_verified": False,
            "right_party_status": "wrong_party",
            "wrong_party_callback_stage": "privacy_notice_given",
            "active_collection_context": {
                "customer": {
                    "variables": {
                        "[COMPANY_NAME]": "EasySecure Financial Services",
                        "[CONTACT_NUMBER]": "+91-1800-555-2002",
                    }
                }
            },
        },
    )
    state = {
        "user_input": "No",
        "memory": memory,
        "plan_proposal": {
            "target": "customer",
            "response_directive": {
                "conversation_objective": "wrong_party_privacy_notice",
                "dialogue_action": "wrong_party_privacy_notice",
                "response_mode": "compliance",
            },
        },
    }

    response = node.execute(state)["response"].lower()

    assert "privacy reasons" in response
    assert "only discuss this directly with rohan gupta" in response
    assert "when would be a good time" not in response
    assert "+91-1800-555-2002" not in response
    assert "37800" not in response
    assert "loan" not in response
    assert "policy number" not in response
    assert "date of birth" not in response


def test_response_node_wrong_party_callback_request_does_not_repeat_privacy_notice() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-wrong-party-followup",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "active_overdue_amount": 37800.0,
            "identity_verified": False,
            "right_party_status": "wrong_party",
            "wrong_party_callback_stage": "awaiting_callback",
            "active_collection_context": {
                "customer": {
                    "variables": {
                        "[COMPANY_NAME]": "EasySecure Financial Services",
                        "[CONTACT_NUMBER]": "+91-1800-555-2002",
                    }
                }
            },
        },
    )
    state = {
        "user_input": "They're not here. What's it about?",
        "memory": memory,
        "plan_proposal": {
            "target": "customer",
            "response_directive": {
                "conversation_objective": "wrong_party_callback_request",
                "dialogue_action": "wrong_party_callback_request",
                "response_mode": "compliance",
            },
        },
    }

    response = node.execute(state)["response"].lower()

    assert "unable to share what the call is about" in response
    assert "easysecure financial services called" in response
    assert "+91-1800-555-2002" in response
    assert "when would be a good time" in response
    assert "only discuss this directly" not in response
    assert "date of birth" not in response
    assert "overdue" not in response


def test_response_node_wrong_party_callback_confirmation_closes_call() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-wrong-party-close",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_case_id": "COLL-1002",
            "identity_verified": False,
            "right_party_status": "wrong_party",
            "wrong_party_callback_stage": "completed",
            "wrong_party_callback_time": "this evening",
            "active_collection_context": {
                "customer": {
                    "variables": {
                        "[COMPANY_NAME]": "EasySecure Financial Services",
                    }
                }
            },
        },
    )
    state = {
        "user_input": "Try this evening",
        "memory": memory,
        "plan_proposal": {
            "target": "customer",
            "response_directive": {
                "conversation_objective": "wrong_party_callback_confirmation",
                "dialogue_action": "wrong_party_callback_confirmation",
                "response_mode": "compliance",
            },
        },
    }

    response = node.execute(state)["response"].lower()

    assert "this evening" in response
    assert "easysecure financial services called" in response
    assert "goodbye" in response
    assert "date of birth" not in response
    assert "overdue" not in response


def test_response_node_callback_confirmation_uses_clean_natural_timing() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-wrong-party-clean-time",
        state={
            "active_customer_name": "Rohan Gupta",
            "identity_verified": False,
            "right_party_status": "wrong_party",
            "wrong_party_callback_stage": "completed",
            "wrong_party_callback_time": "at 5:30 PM today",
            "active_collection_context": {
                "customer": {
                    "variables": {
                        "[COMPANY_NAME]": "EasySecure Financial Services",
                    }
                }
            },
        },
    )
    state = {
        "user_input": "he is not here now, please try at 5:30pm in evening today",
        "memory": memory,
        "plan_proposal": {
            "target": "customer",
            "response_directive": {
                "conversation_objective": "wrong_party_callback_confirmation",
                "dialogue_action": "wrong_party_callback_confirmation",
                "response_mode": "compliance",
            },
        },
    }

    response = node.execute(state)["response"]

    assert "reach Rohan Gupta at 5:30 PM today" in response
    assert "he is not here now" not in response
    assert response.count("Thank you") == 1


def test_response_node_closing_acknowledgement_does_not_repeat_callback() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-wrong-party-ack",
        state={
            "active_customer_name": "Rohan Gupta",
            "wrong_party_callback_stage": "completed",
            "wrong_party_callback_time": "at 5 PM today",
        },
    )
    state = {
        "user_input": "sure, thank you",
        "memory": memory,
        "plan_proposal": {
            "target": "customer",
            "response_directive": {
                "conversation_objective": "wrong_party_closing_acknowledgement",
                "dialogue_action": "wrong_party_closing_acknowledgement",
                "response_mode": "compliance",
            },
        },
    }

    update = node.execute(state)

    assert update["response"] == "You're welcome. Goodbye."
    assert "5 PM" not in update["response"]
    assert update["conversation_complete"] is False
    assert update["conversation_closing"] is True
    assert update["terminate_call"] is True
    assert update["termination_grace_seconds"] == 3.0


def test_response_node_revised_callback_confirms_only_new_time() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-wrong-party-revision",
        state={
            "active_customer_name": "Rohan Gupta",
            "wrong_party_callback_stage": "completed",
            "wrong_party_callback_time": "at 9 PM",
        },
    )
    state = {
        "user_input": "No, his flight is late, try at 9pm.",
        "memory": memory,
        "plan_proposal": {
            "target": "customer",
            "response_directive": {
                "conversation_objective": "wrong_party_callback_revision_confirmation",
                "dialogue_action": "wrong_party_callback_revision_confirmation",
                "response_mode": "compliance",
            },
        },
    }

    response = node.execute(state)["response"]

    assert "at 9 PM" in response
    assert "5 PM" not in response
    assert "update the callback" in response


def test_response_node_missing_directive_does_not_infer_hardship_objective() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-no-directive",
        state={
            "active_customer_name": "Aditi",
            "active_case_id": "COLL-1001",
            "active_overdue_amount": 1200.0,
            "conversation_mode": "hardship_negotiation",
            "negotiation_stage": "assessing_capacity",
            "customer_payment_posture": "cannot_pay",
            "hardship_context": {
                "hardship_detected": True,
                "hardship_reason": "job_loss",
                "confidence": 0.96,
            },
            "response_mode": "empathetic",
            "active_dialogue_owner": "plan_proposal",
            "identity_verified": True,
        },
    )
    state = {
        "user_input": "I lost my job",
        "memory": memory,
        "plan_proposal": {
            "target": "customer",
            "intent": "generic_plan",
        },
    }

    update = node.execute(state)
    response = update["response"].lower()

    assert "monthly amount" not in response
    assert "pay now" not in response
    assert "please let me know how you would like to proceed" in response
    assert update["response_render_debug"]["template_selected"] == "safe_follow_up"
    assert update["response_render_debug"]["renderer_fallback_used"] is True


def test_response_node_minimal_safety_cleanup_strips_internal_leakage() -> None:
    node = _build_node()

    cleaned = node._apply_minimal_safety_cleanup(
        text="Please wait while I evaluate. ```json {\"foo\": \"bar\"}```",
        context={},
        directive={},
    )

    lowered = cleaned.lower()
    assert "please wait while i evaluate" not in lowered
    assert "```" not in cleaned


def test_response_node_validator_blocks_unresolved_placeholders() -> None:
    node = _build_node()

    validation = node._validate_response_against_directive(
        text="Hello [name], please confirm {missing_fields}.",
        directive={
            "template_id": "verification_request",
            "response_target": "customer",
            "tone": "compliance",
            "render_variables": {},
            "response_constraints": {"avoid_placeholders": True},
            "fallback_template_id": "verification_request",
        },
        context={
            "response_target": "customer",
            "verification_context": {"identity_verified": False},
        },
    )

    assert validation["text"] is None
    assert "unresolved_placeholders" in validation["forbidden_actions_blocked"]


def test_response_node_validator_blocks_dues_before_verification() -> None:
    node = _build_node()

    validation = node._validate_response_against_directive(
        text="Your overdue amount is INR 1200.00.",
        directive={
            "template_id": "dues_explanation",
            "response_target": "customer",
            "tone": "informational",
            "render_variables": {},
            "response_constraints": {"no_dues_before_verification": True},
            "fallback_template_id": "dues_explanation",
        },
        context={
            "response_target": "customer",
            "verification_context": {"identity_verified": False},
        },
    )

    assert validation["text"] is None
    assert "disclose_dues_before_verification" in validation["forbidden_actions_blocked"]


def test_response_node_validator_blocks_mixed_discount_hold_offer() -> None:
    node = _build_node()

    validation = node._validate_response_against_directive(
        text=(
            "I can offer a 10% discount and also place the premium on hold for 2 months. "
            "Would that help?"
        ),
        directive={
            "template_id": "installment_discount_offer",
            "response_target": "customer",
            "tone": "empathetic",
            "render_variables": {
                "discount_pct_text": "10",
                "original_amount_text": "37800.00",
                "revised_amount_text": "34020.00",
            },
            "response_constraints": {},
            "fallback_template_id": "installment_discount_offer",
        },
        context={
            "response_target": "customer",
            "verification_context": {"identity_verified": True},
        },
    )

    assert validation["text"] is None
    assert "mixed_offer_with_hold" in validation["forbidden_actions_blocked"]


def test_response_node_negotiation_mode_does_not_add_empathy_language() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-negotiation-tone",
        state={
            "active_customer_name": "Aditi",
            "active_case_id": "COLL-1001",
            "active_overdue_amount": 1200.0,
            "identity_verified": True,
        },
    )
    state = {
        "user_input": "What arrangements can I request?",
        "memory": memory,
        "plan_proposal": {
            "target": "customer",
            "intent": "generic_plan",
            "response_directive": {
                "conversation_objective": "present_arrangement_options",
                "dialogue_action": "discuss_arrangement",
                "response_mode": "negotiation",
                "required_response_elements": ["discuss_arrangement"],
                "forbidden_dialogue_actions": ["restart_collections_menu"],
                "allowed_dialogue_actions": ["discuss_arrangement"],
                "customer_facing_goal": "Continue arrangement discussion directly.",
                "handoff_target": None,
            },
        },
    }

    response = node.execute(state)["response"].lower()

    assert "sorry" not in response
    assert "appreciate you sharing" not in response
    assert "installment" in response or "arrangement" in response


def test_response_node_compliance_mode_stays_verification_focused() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-compliance-tone",
        state={
            "active_customer_name": "Aditi",
            "active_case_id": "COLL-1001",
            "active_overdue_amount": 1200.0,
            "identity_verified": False,
            "active_verification_required_fields": ["dob"],
            "verification_missing_fields": ["dob"],
            "verification_entities": {},
        },
    )
    state = {
        "user_input": "Can you tell me the dues?",
        "memory": memory,
        "plan_proposal": {
            "target": "customer",
            "intent": "generic_plan",
            "response_directive": {
                "conversation_objective": "collect_verification",
                "dialogue_action": "ask_verification",
                "response_mode": "compliance",
                "required_response_elements": ["ask_verification"],
                "forbidden_dialogue_actions": ["disclose_dues_before_verification"],
                "allowed_dialogue_actions": ["ask_verification"],
                "customer_facing_goal": "Ask only for the missing verification detail.",
                "handoff_target": None,
            },
        },
    }

    response = node.execute(state)["response"].lower()

    assert "sorry" not in response
    assert "overdue amount" not in response
    assert "date of birth" in response


def test_response_node_uses_recent_conversation_window_from_history() -> None:
    node = _build_node()
    memory = WorkingMemory(
        session_id="response-recent-conversation",
        state={
            "active_customer_name": "Aditi",
            "conversation_history": [
                {"role": "customer", "content": "turn1 customer"},
                {"role": "agent", "content": "turn1 agent"},
                {"role": "customer", "content": "turn2 customer"},
                {"role": "agent", "content": "turn2 agent"},
                {"role": "customer", "content": "turn3 customer"},
                {"role": "agent", "content": "turn3 agent"},
                {"role": "customer", "content": "turn4 customer"},
                {"role": "agent", "content": "turn4 agent"},
            ],
        },
    )
    state = {
        "user_input": "current user input",
        "memory": memory,
        "plan_proposal": {"target": "customer", "intent": "generic_plan"},
    }

    context = node._resolve_render_context(state=state, proposal=state["plan_proposal"])

    assert context["recent_conversation"] == [
        {"role": "customer", "content": "turn2 customer"},
        {"role": "agent", "content": "turn2 agent"},
        {"role": "customer", "content": "turn3 customer"},
        {"role": "agent", "content": "turn3 agent"},
        {"role": "customer", "content": "turn4 customer"},
        {"role": "agent", "content": "turn4 agent"},
    ]
