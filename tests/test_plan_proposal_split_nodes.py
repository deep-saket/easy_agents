from __future__ import annotations

from agents.collection_agent.agent import CollectionAgent
from agents.collection_agent.nodes.plan_proposal_directive_node import PlanProposalDirectiveNode
from agents.collection_agent.nodes.plan_proposal_graph_node import PlanProposalGraphNode
from agents.collection_agent.nodes.plan_proposal_state_node import PlanProposalStateNode
from agents.collection_agent.nodes.plan_proposal_utils import (
    finalize_conversation_memory,
    is_right_party_denial,
)
from agents.collection_agent.nodes.callback_time_extractor import extract_callback_time
from src.nodes.base import BaseGraphNode
from src.memory.types import WorkingMemory


def _memory(state: dict) -> WorkingMemory:
    return WorkingMemory(session_id="plan-split", state=state)


def _base_state(memory: WorkingMemory, user_input: str = "hello") -> dict:
    return {
        "user_input": user_input,
        "memory": memory,
        "steps": 0,
        "observation": None,
        "observations": [],
    }


def _run_split_chain(base_memory_state: dict, user_input: str) -> tuple[dict, dict, dict]:
    memory = _memory(base_memory_state)
    state = _base_state(memory, user_input=user_input)
    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)
    state_update = state_node.execute(state)
    graph_input = {**state, **state_update}
    graph_update = graph_node.execute(graph_input)
    directive_input = {**state, **state_update, **graph_update}
    directive_update = directive_node.execute(directive_input)
    return state_update, graph_update, directive_update


def test_split_plan_nodes_use_base_graph_inheritance_only() -> None:
    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)

    for node in (state_node, graph_node, directive_node):
        assert isinstance(node, BaseGraphNode)
        assert type(node).__bases__ == (BaseGraphNode,)


def test_plan_proposal_state_node_outputs_signals_and_mode() -> None:
    memory = _memory(
        {
            "mode": "strict_collections",
            "active_case_id": "COLL-1001",
            "active_user_id": "USER-1",
            "active_customer_name": "Aditi",
            "active_overdue_amount": 1200.0,
            "conversation_mode": "hardship_negotiation",
            "negotiation_stage": "assessing_capacity",
            "customer_payment_posture": "partial_now",
            "customer_payment_capacity": 3000.0,
            "customer_payment_capacity_pct": 25.0,
            "discount_stage": "requested",
            "discount_requested": True,
            "counter_offer_present": True,
            "hardship_context": {
                "hardship_detected": True,
                "hardship_reason": "job_loss",
                "confidence": 0.96,
            },
            "response_mode": "empathetic",
            "active_dialogue_owner": "plan_proposal",
            "identity_verified": True,
        }
    )
    node = PlanProposalStateNode(llm=None, strict_llm_mode=False)

    update = node.execute(_base_state(memory, user_input="I lost my job"))

    assert update["plan_mode"] == "hardship_negotiation"
    assert update["plan_signals"]["hardship_signal"] is True
    assert update["plan_signals"]["suggested_plan_mode"] == "hardship_negotiation"
    assert update["plan_signals"]["customer_payment_posture"] == "partial_now"
    assert update["plan_signals"]["customer_payment_capacity"] == 3000.0
    assert update["plan_signals"]["customer_payment_capacity_pct"] == 25.0
    assert update["plan_signals"]["discount_stage"] == "requested"
    assert update["plan_signals"]["discount_requested"] is True
    assert update["plan_signals"]["counter_offer_present"] is True
    assert update["effective_identity_verified"] is True


def test_plan_proposal_graph_node_keeps_identity_gate_in_plan_tree() -> None:
    state_update, graph_update, _ = _run_split_chain(
        {
            "mode": "strict_collections",
            "active_case_id": "COLL-1001",
            "active_user_id": "USER-1",
            "active_customer_name": "Aditi",
            "active_overdue_amount": 1200.0,
            "active_verification_required_fields": ["dob", "phone"],
            "verification_entities": {"dob": "1991-08-19"},
            "verification_missing_fields": ["phone"],
            "verification_verified_fields": ["dob"],
            "identity_verified": False,
        },
        user_input="hello",
    )

    plan = graph_update["conversation_plan"]
    assert state_update["effective_identity_verified"] is False
    assert plan["current_node_id"] == "verify_identity"
    assert graph_update["plan_tree_context"]["current_node_id"] == "verify_identity"


def test_plan_proposal_graph_marks_case_context_done_after_advancing_past_root() -> None:
    memory = _memory(
        {
            "mode": "strict_collections",
            "active_case_id": "COLL-1001",
            "active_user_id": "USER-1",
            "active_customer_name": "Aditi",
            "active_overdue_amount": 1200.0,
            "active_verification_required_fields": ["dob", "phone"],
            "verification_missing_fields": [],
            "verification_verified_fields": ["dob", "phone"],
            "identity_verified": True,
        }
    )
    state = _base_state(memory, user_input="hello")
    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)

    state_update = state_node.execute(state)
    graph_update = graph_node.execute({**state, **state_update})

    plan = graph_update["conversation_plan"]
    nodes = {node["id"]: node for node in plan["nodes"]}
    assert plan["current_node_id"] == "explain_dues"
    assert plan["step_markers"]["open_and_context"]["state"] == "done"
    assert nodes["open_and_context"]["status"] == "done"


def test_bare_no_is_detected_as_right_party_denial_only_during_confirmation() -> None:
    assert is_right_party_denial("No", awaiting_confirmation=True) is True
    assert is_right_party_denial("No", awaiting_confirmation=False) is False


def test_callback_time_extractor_cleans_conversational_sentence() -> None:
    assert (
        extract_callback_time("he is not here now, please try at 5:30pm in evening today")
        == "at 5:30 PM today"
    )
    assert extract_callback_time("try this evening") == "this evening"
    assert extract_callback_time("he is not here, try at 5 today in evening") == "at 5 PM today"
    assert extract_callback_time("sorry he may be late so call at 9am tommarrow") == "at 9 AM tomorrow"


def test_callback_time_extractor_uses_grounded_llm_fallback() -> None:
    class CallbackLLM:
        def structured_generate(self, prompt: str, schema: type, **_: object):
            assert "after my shift" in prompt
            return schema(
                callback_time="after my shift",
                confidence=0.92,
                needs_clarification=False,
            )

    assert (
        extract_callback_time("Please call him after my shift", llm=CallbackLLM())
        == "after my shift"
    )


def test_callback_time_extractor_rejects_vague_llm_result() -> None:
    class VagueCallbackLLM:
        def structured_generate(self, prompt: str, schema: type, **_: object):
            return schema(
                callback_time="later",
                confidence=0.95,
                needs_clarification=False,
            )

    assert extract_callback_time("Maybe sometime later", llm=VagueCallbackLLM()) == ""


def test_wrong_party_callback_flow_reaches_explicit_closing_node() -> None:
    memory = _memory(
        {
            "mode": "strict_collections",
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "active_customer_name": "Rohan Gupta",
            "active_overdue_amount": 37800.0,
            "active_verification_required_fields": ["dob", "phone"],
            "verification_missing_fields": ["dob", "phone"],
            "identity_verified": False,
            "right_party_status": "awaiting_confirmation",
        }
    )
    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)

    first_state = _base_state(memory, user_input="No")
    first_state_update = state_node.execute(first_state)
    first_graph_update = graph_node.execute({**first_state, **first_state_update})
    first_directive_update = directive_node.execute(
        {**first_state, **first_state_update, **first_graph_update}
    )

    first_directive = first_directive_update["plan_proposal"]["response_directive"]
    first_plan = first_graph_update["conversation_plan"]
    assert first_directive["conversation_objective"] == "wrong_party_privacy_notice"
    assert first_plan["current_node_id"] == "wrong_party_callback"
    assert first_plan["step_markers"]["verify_identity"]["state"] == "skipped"
    assert first_plan["step_markers"]["explain_dues"]["state"] == "skipped"
    assert first_plan["step_markers"]["collect_payment_intent"]["state"] == "skipped"
    assert first_plan["step_markers"]["evaluate_assistance"]["state"] == "skipped"
    assert first_plan["step_markers"]["resolve_outcome"]["state"] == "skipped"
    first_nodes = {node["id"]: node for node in first_plan["nodes"]}
    assert first_nodes["wrong_party_callback"]["status"] == "in_progress"
    assert first_nodes["explain_dues"]["status"] == "skipped"
    assert memory.state["right_party_status"] == "wrong_party"
    assert memory.state["wrong_party_callback_stage"] == "privacy_notice_given"

    second_state = _base_state(
        memory,
        user_input="They're not here right now. Can I take a message? What's it about?",
    )
    second_state_update = state_node.execute(second_state)
    second_graph_update = graph_node.execute({**second_state, **second_state_update})
    second_directive_update = directive_node.execute(
        {**second_state, **second_state_update, **second_graph_update}
    )
    second_directive = second_directive_update["plan_proposal"]["response_directive"]
    assert second_directive["conversation_objective"] == "wrong_party_callback_request"
    assert memory.state["wrong_party_callback_stage"] == "awaiting_callback"

    third_state = _base_state(memory, user_input="Try this evening")
    third_state_update = state_node.execute(third_state)
    third_graph_update = graph_node.execute({**third_state, **third_state_update})
    third_directive_update = directive_node.execute(
        {**third_state, **third_state_update, **third_graph_update}
    )

    plan = third_graph_update["conversation_plan"]
    third_directive = third_directive_update["plan_proposal"]["response_directive"]
    assert plan["current_node_id"] == "close_conversation"
    assert plan["status"] == "active"
    assert plan["step_markers"]["verify_identity"]["state"] == "skipped"
    assert plan["step_markers"]["wrong_party_callback"]["state"] == "done"
    assert plan["step_markers"]["close_conversation"]["state"] == "pending"
    plan_nodes = {node["id"]: node for node in plan["nodes"]}
    assert plan_nodes["close_conversation"]["status"] == "in_progress"
    assert third_directive["conversation_objective"] == "wrong_party_callback_confirmation"
    assert memory.state["wrong_party_callback_time"] == "this evening"

    retry_state = _base_state(memory, user_input="Try this evening")
    retry_state_update = state_node.execute(retry_state)
    retry_graph_update = graph_node.execute({**retry_state, **retry_state_update})
    retry_directive_update = directive_node.execute(
        {**retry_state, **retry_state_update, **retry_graph_update}
    )

    retry_plan = retry_graph_update["conversation_plan"]
    retry_directive = retry_directive_update["plan_proposal"]["response_directive"]
    assert retry_plan["current_node_id"] == "close_conversation"
    assert retry_plan["status"] == "active"
    assert retry_directive["conversation_objective"] == "wrong_party_closing_acknowledgement"

    revision_state = _base_state(
        memory,
        user_input="No, his flight is running late, so please try at 9pm.",
    )
    revision_state_update = state_node.execute(revision_state)
    revision_graph_update = graph_node.execute({**revision_state, **revision_state_update})
    revision_directive_update = directive_node.execute(
        {**revision_state, **revision_state_update, **revision_graph_update}
    )
    revision_directive = revision_directive_update["plan_proposal"]["response_directive"]
    assert revision_directive["conversation_objective"] == "wrong_party_callback_revision_confirmation"
    assert memory.state["wrong_party_callback_time"] == "at 9 PM"

    finalize_conversation_memory(memory)
    closed_plan = memory.state["active_conversation_plan"]
    closed_nodes = {node["id"]: node for node in closed_plan["nodes"]}
    assert closed_plan["status"] == "completed"
    assert closed_plan["step_markers"]["close_conversation"]["state"] == "done"
    assert closed_nodes["close_conversation"]["status"] == "done"
    final_snapshot = closed_plan["timeline_snapshots"][-1]
    final_snapshot_nodes = {
        node["id"]: node for node in final_snapshot["plan"]["nodes"]
    }
    assert final_snapshot["status"] == "completed"
    assert final_snapshot["current_node_id"] == "close_conversation"
    assert final_snapshot["update"]["origin"] == "conversation_manager_timer"
    assert final_snapshot["plan"]["status"] == "completed"
    assert final_snapshot_nodes["close_conversation"]["status"] == "done"


def test_plan_proposal_directive_node_returns_response_directive() -> None:
    _, graph_update, directive_update = _run_split_chain(
        {
            "mode": "strict_collections",
            "active_case_id": "COLL-1001",
            "active_user_id": "USER-1",
            "active_customer_name": "Aditi",
            "active_overdue_amount": 1200.0,
            "active_verification_required_fields": ["dob", "phone"],
            "verification_entities": {"dob": "1991-08-19"},
            "verification_missing_fields": ["phone"],
            "verification_verified_fields": ["dob"],
            "identity_verified": False,
        },
        user_input="hello",
    )

    proposal = directive_update["plan_proposal"]
    directive = proposal["response_directive"]
    assert "plan_tree_update" not in proposal
    assert graph_update["conversation_plan"]["current_node_id"] == "verify_identity"
    assert directive["conversation_objective"] == "collect_verification"
    assert directive["dialogue_action"] == "ask_verification"


def test_plan_proposal_directive_uses_hardship_arrangement_directive() -> None:
    _, _, directive_update = _run_split_chain(
        {
            "mode": "strict_collections",
            "active_case_id": "COLL-1001",
            "active_user_id": "USER-1",
            "active_customer_name": "Aditi",
            "active_overdue_amount": 1200.0,
            "active_verification_required_fields": ["dob", "phone"],
            "identity_verified": True,
            "conversation_mode": "hardship_negotiation",
            "negotiation_stage": "assessing_capacity",
            "customer_payment_posture": "negotiating",
            "hardship_context": {
                "hardship_detected": True,
                "hardship_reason": "job_loss",
                "confidence": 0.96,
            },
            "response_mode": "empathetic",
            "active_dialogue_owner": "plan_proposal",
        },
        user_input="I lost my job",
    )

    directive = directive_update["plan_proposal"]["response_directive"]
    assert directive_update["response_target"] == "customer"
    assert directive["conversation_objective"] == "assess_affordability"
    assert directive["dialogue_action"] == "ask_affordable_amount"
    assert "explain_applicable_policy_options" not in directive["required_response_elements"]
    assert "ask_pay_now_or_arrangement" in directive["forbidden_dialogue_actions"]
    assert "amount or payment date" in directive["customer_facing_goal"].lower()


def test_job_loss_routes_to_data_driven_hold_then_confirmation() -> None:
    hold_program = {
        "program_id": "PREMIUM_HOLD_001",
        "program_type": "premium_hold",
        "eligible_products": ["personal_loan"],
        "eligible_loan_ids": ["LOAN-3002"],
        "hardship_reasons": ["job_loss"],
        "max_hold_months": 2,
        "benefits_remain_active": True,
        "confirmation_channels": ["sms", "email"],
        "confirmation_sla_hours": 24,
    }
    memory = _memory(
        {
            "mode": "hardship_negotiation",
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "active_customer_name": "Rohan Gupta",
            "identity_verified": True,
            "conversation_mode": "hardship_negotiation",
            "negotiation_stage": "discovering_hardship",
            "customer_payment_posture": "cannot_pay",
            "hardship_context": {
                "hardship_detected": True,
                "hardship_reason": "job_loss",
                "confidence": 1.0,
            },
            "assistance_programs": [hold_program],
            "active_collection_context": {
                "case": {
                    "case_id": "COLL-1002",
                    "loan_id": "LOAN-3002",
                    "product": "personal_loan",
                },
                "customer": {
                    "variables": {
                        "[REF_NUMBER]": "COLL-1002",
                    }
                },
            },
        }
    )
    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)

    offer_state = _base_state(memory, user_input="I recently lost my job")
    offer_prepared = state_node.execute(offer_state)
    offer_graph = graph_node.execute({**offer_state, **offer_prepared})
    offer_update = directive_node.execute({**offer_state, **offer_prepared, **offer_graph})

    assert offer_graph["conversation_plan"]["current_node_id"] == "resolution_offer"
    assert offer_update["plan_proposal"]["conversation_objective"] == "hardship_hold_offer"
    assert memory.state["hardship_hold_stage"] == "offered"

    memory.set_state(
        hardship_hold_stage="confirmed",
        hardship_hold_details={
            "hold_months": 2,
            "reference_number": "HOLD-A1B2C3D4E5",
            "status": "active",
            "sms_confirmation": {"status": "sent"},
            "email_confirmation": {"status": "sent"},
        },
    )
    accepted_state = _base_state(memory, user_input="Yes, that would really help")
    accepted_prepared = state_node.execute(accepted_state)
    accepted_graph = graph_node.execute({**accepted_state, **accepted_prepared})
    accepted_update = directive_node.execute(
        {**accepted_state, **accepted_prepared, **accepted_graph}
    )

    assert accepted_graph["conversation_plan"]["current_node_id"] == "confirmation"
    assert accepted_update["plan_proposal"]["conversation_objective"] == "hardship_hold_confirmation"
    assert memory.state["hardship_hold_stage"] == "confirmed"
    assert memory.state["hardship_hold_details"]["hold_months"] == 2
    assert memory.state["hardship_hold_details"]["reference_number"] == "HOLD-A1B2C3D4E5"


def test_plan_proposal_directive_discount_handoff_remains_intact() -> None:
    _, _, directive_update = _run_split_chain(
        {
            "mode": "strict_collections",
            "active_case_id": "COLL-1001",
            "active_user_id": "USER-1",
            "active_customer_name": "Aditi",
            "active_overdue_amount": 1200.0,
            "identity_verified": True,
            "conversation_mode": "collections",
            "negotiation_stage": "none",
            "customer_payment_posture": "unknown",
            "hardship_context": {
                "hardship_detected": False,
                "hardship_reason": None,
                "confidence": 0.0,
            },
            "response_mode": "informational",
            "active_dialogue_owner": "collections",
        },
        user_input="Can I get a discount or waiver?",
    )

    proposal = directive_update["plan_proposal"]
    assert proposal["target"] == "discount_planning_agent"
    assert directive_update["response_target"] == "discount_planning_agent"
    assert directive_update["handoff_payload"]["case_id"] == "COLL-1001"


def test_plan_proposal_directive_routes_explicit_settlement_to_discount_planning() -> None:
    _, _, directive_update = _run_split_chain(
        {
            "mode": "strict_collections",
            "active_case_id": "COLL-1001",
            "active_user_id": "USER-1",
            "active_customer_name": "Aditi",
            "active_overdue_amount": 1200.0,
            "identity_verified": True,
            "conversation_mode": "collections",
            "negotiation_stage": "evaluating_options",
            "customer_payment_posture": "partial_now",
            "customer_payment_capacity": 2000.0,
            "discount_stage": "requested",
            "discount_requested": True,
            "response_mode": "negotiation",
            "active_dialogue_owner": "plan_proposal",
        },
        user_input="I can pay 2000 today if you can settle this.",
    )

    assert directive_update["response_target"] == "discount_planning_agent"
    assert directive_update["handoff_payload"]["customer_payment_capacity"] == 2000.0
    assert directive_update["handoff_payload"]["discount_stage"] == "requested"
    assert directive_update["handoff_payload"]["customer_payment_posture"] == "partial_now"


def test_plan_proposal_directive_keeps_standard_partial_payment_local() -> None:
    _, _, directive_update = _run_split_chain(
        {
            "mode": "strict_collections",
            "active_case_id": "COLL-1002",
            "active_user_id": "USER-2",
            "active_customer_name": "Rohan",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
            "conversation_mode": "hardship_negotiation",
            "negotiation_stage": "assessing_capacity",
            "customer_payment_posture": "partial_now",
            "customer_payment_capacity": 5000.0,
            "discount_stage": "none",
            "discount_requested": False,
            "hardship_context": {
                "hardship_detected": True,
                "hardship_reason": "job_loss",
                "confidence": 1.0,
            },
            "response_mode": "empathetic",
            "active_dialogue_owner": "plan_proposal",
        },
        user_input="I can manage 5000 this month.",
    )

    directive = directive_update["plan_proposal"]["response_directive"]
    assert directive_update["response_target"] == "customer"
    assert directive["conversation_objective"] in {"assess_affordability", "present_arrangement_options"}
    assert directive_update.get("handoff_payload") is None


def test_plan_proposal_directive_does_not_rehandoff_generic_hardship_acceptance() -> None:
    _, _, directive_update = _run_split_chain(
        {
            "mode": "hardship_negotiation",
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "active_customer_name": "Rohan",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
            "conversation_mode": "hardship_negotiation",
            "negotiation_stage": "negotiating_plan",
            "customer_payment_posture": "negotiating",
            "customer_payment_posture_history": ["cannot_pay", "negotiating"],
            "discount_stage": "offered",
            "discount_requested": True,
            "discount_offered": True,
            "counter_offer_present": False,
            "hardship_context": {
                "hardship_detected": True,
                "hardship_reason": "job_loss",
                "confidence": 1.0,
            },
            "response_mode": "empathetic",
            "active_dialogue_owner": "plan_proposal",
        },
        user_input="Yes, that would really help.",
    )

    assert directive_update["response_target"] == "customer"
    assert directive_update.get("handoff_payload") is None


def test_plan_proposal_directive_termination_remains_intact() -> None:
    _, graph_update, directive_update = _run_split_chain(
        {
            "mode": "strict_collections",
            "active_case_id": "COLL-1001",
            "active_user_id": "USER-1",
            "active_customer_name": "Aditi",
            "active_overdue_amount": 1200.0,
            "identity_verified": True,
            "conversation_mode": "collections",
            "negotiation_stage": "none",
            "customer_payment_posture": "unknown",
            "hardship_context": {
                "hardship_detected": False,
                "hardship_reason": None,
                "confidence": 0.0,
            },
            "response_mode": "informational",
            "active_dialogue_owner": "collections",
        },
        user_input="bye",
    )

    proposal = directive_update["plan_proposal"]
    assert proposal["intent"] == "conversation_termination"
    assert "plan_tree_update" not in proposal
    assert graph_update["conversation_plan"]["current_node_id"] == "close_conversation"


def test_collection_agent_graph_wires_split_plan_nodes() -> None:
    agent = CollectionAgent.from_local_files()
    graph = agent.graph.get_graph()
    node_ids = set(graph.nodes.keys())
    edge_pairs = {(edge.source, edge.target) for edge in graph.edges}

    assert "plan_proposal" not in node_ids
    assert {"plan_proposal_state", "plan_proposal_graph", "plan_proposal_directive"}.issubset(node_ids)
    assert ("pre_plan_intent", "plan_proposal_state") in edge_pairs
    assert ("post_memory_plan_intent", "plan_proposal_state") in edge_pairs
    assert ("post_verification_intent", "plan_proposal_state") in edge_pairs
    assert ("react", "plan_proposal_state") in edge_pairs
    assert ("reflect", "plan_proposal_state") in edge_pairs
    assert ("plan_proposal_state", "plan_proposal_graph") in edge_pairs
    assert ("plan_proposal_graph", "plan_proposal_directive") in edge_pairs
    assert ("plan_proposal_directive", "reflect") in edge_pairs
