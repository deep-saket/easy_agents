from __future__ import annotations

import json
from pathlib import Path

from agents.collection_agent.nodes.collection_react_node import CollectionReactNode
from agents.collection_agent.nodes.collection_response_node import CollectionResponseNode
from agents.collection_agent.nodes.negotiation_classification_node import NegotiationClassificationNode
from agents.collection_agent.nodes.plan_proposal_directive_node import PlanProposalDirectiveNode
from agents.collection_agent.nodes.plan_proposal_graph_node import PlanProposalGraphNode
from agents.collection_agent.nodes.plan_proposal_state_node import PlanProposalStateNode
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.email_confirmation_send_tool import EmailConfirmationSendTool
from agents.collection_agent.tools.installment_discount_apply_tool import InstallmentDiscountApplyTool
from agents.collection_agent.tools.installment_discount_evaluate_tool import InstallmentDiscountEvaluateTool
from agents.collection_agent.tools.sms_confirmation_send_tool import SMSConfirmationSendTool
from src.memory.types import WorkingMemory
from src.nodes.tool_execution_node import ToolExecutionNode
from src.tools.executor import ToolExecutor
from src.tools.registry import ToolRegistry


def _store(tmp_path: Path) -> CollectionDataStore:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "customers.json").write_text(
        json.dumps(
            [
                {
                    "customer_id": "CUST-2002",
                    "phone": "+919900001002",
                    "email": "rohan.gupta@example.com",
                }
            ]
        ),
        encoding="utf-8",
    )
    (data_dir / "assistance_programs.json").write_text(
        json.dumps(
            [
                {
                    "program_id": "JOB_LOSS_INSTALLMENT_DISCOUNT_001",
                    "program_type": "installment_discount",
                    "eligible_loan_ids": ["LOAN-3002"],
                    "hardship_reasons": ["job_loss"],
                    "discount_pct": 10,
                    "requires_manager_approval": False,
                    "review_after_months": 3,
                }
            ]
        ),
        encoding="utf-8",
    )
    (data_dir / "cases.json").write_text(
        json.dumps(
            [
                {
                    "case_id": "COLL-1002",
                    "customer_id": "CUST-2002",
                    "loan_id": "LOAN-3002",
                }
            ]
        ),
        encoding="utf-8",
    )
    return CollectionDataStore(base_dir=tmp_path)


def _registry(store: CollectionDataStore) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(InstallmentDiscountEvaluateTool(store=store))
    registry.register(InstallmentDiscountApplyTool(store=store))
    registry.register(SMSConfirmationSendTool(store=store))
    registry.register(EmailConfirmationSendTool(store=store))
    return registry


def test_job_loss_uncertainty_evaluates_and_applies_discount(tmp_path: Path) -> None:
    store = _store(tmp_path)
    registry = _registry(store)
    react = CollectionReactNode(
        llm=None,
        available_tools=registry.build_catalog(),
        tool_registry=registry,
        max_steps=8,
    )
    executor = ToolExecutionNode(executor=ToolExecutor(registry=registry))
    program = store.load_assistance_programs()[0]
    memory = WorkingMemory(
        session_id="discount-flow",
        state={
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "active_loan_id": "LOAN-3002",
            "active_overdue_amount": 37800.0,
            "hardship_hold_stage": "offered",
            "hardship_context": {
                "hardship_detected": True,
                "hardship_reason": "job_loss",
            },
            "assistance_programs": [program],
            "active_collection_context": {"case": {"loan_id": "LOAN-3002"}},
        },
    )

    uncertainty_state = {
        "session_id": "discount-flow",
        "case_id": "COLL-1002",
        "user_id": "CUST-2002",
        "user_input": "I'm not sure I can manage even after 2 months.",
        "memory": memory,
        "steps": 0,
        "observations": [],
    }
    memory.set_state(hold_response="uncertain")
    evaluate_update = react.execute(uncertainty_state)
    uncertainty_state.update(evaluate_update)
    assert evaluate_update["decision"].tool_call.tool_name == "installment_discount_evaluate"
    uncertainty_state.update(executor.execute(uncertainty_state))
    offer_update = react.execute(uncertainty_state)
    assert offer_update["decision"].done is True
    assert memory.state["discount_stage"] == "offered"
    assert memory.state["hardship_hold_stage"] == "superseded"
    assert memory.state["installment_discount_details"]["revised_amount"] == 34020.0

    memory.set_state(discount_stage="accepted", discount_accepted=True)
    memory.set_state(discount_response="accepted")
    acceptance_state = {
        "session_id": "discount-flow",
        "case_id": "COLL-1002",
        "user_id": "CUST-2002",
        "user_input": "Yes, that would make a real difference.",
        "memory": memory,
        "steps": 0,
        "observations": [],
    }
    executed: list[str] = []
    for _ in range(3):
        react_update = react.execute(acceptance_state)
        acceptance_state.update(react_update)
        executed.append(react_update["decision"].tool_call.tool_name)
        acceptance_state.update(executor.execute(acceptance_state))
    final_update = react.execute(acceptance_state)

    details = memory.state["installment_discount_details"]
    assert executed == [
        "installment_discount_apply",
        "sms_confirmation_send",
        "email_confirmation_send",
    ]
    assert "premium_hold_create" not in executed
    assert final_update["decision"].done is True
    assert memory.state["discount_stage"] == "confirmed"
    assert details["reference_number"].startswith("DISC-")
    assert details["original_amount"] == 37800.0
    assert details["discount_pct"] == 10.0
    assert details["revised_amount"] == 34020.0
    assert details["sms_confirmation"]["status"] == "sent"
    assert details["email_confirmation"]["status"] == "sent"
    assert store.load_runtime("installment_discounts.json")[0]["reference_number"] == details["reference_number"]


def test_discount_offer_confirmation_and_named_closing() -> None:
    node = CollectionResponseNode(llm=None, strict_llm_mode=False)
    memory = WorkingMemory(
        session_id="discount-response",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_overdue_amount": 37800.0,
            "installment_discount_details": {
                "reference_number": "DISC-A1B2C3D4E5",
                "status": "applied",
                "original_amount": 37800.0,
                "discount_pct": 10.0,
                "discount_amount": 3780.0,
                "revised_amount": 34020.0,
                "review_after_months": 3,
                "sms_confirmation": {"status": "sent"},
                "email_confirmation": {"status": "sent"},
            },
        },
    )

    offer = node.execute(
        {
            "user_input": "I'm not sure I can manage even after 2 months.",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "installment_discount_offer",
                    "dialogue_action": "offer_installment_discount",
                    "response_mode": "empathetic",
                },
            },
        }
    )["response"]
    assert "10% discount" in offer
    assert "37800.00" in offer
    assert "34020.00" in offer

    confirmation = node.execute(
        {
            "user_input": "Yes, that would make a real difference.",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "installment_discount_confirmation",
                    "dialogue_action": "confirm_installment_discount",
                    "response_mode": "empathetic",
                },
            },
        }
    )["response"]
    assert "reference number is DISC-A1B2C3D4E5" in confirmation
    assert "revised amount is 34020.00" in confirmation
    assert "sent by SMS and email" in confirmation
    assert "3 months" in confirmation

    closing = node.execute(
        {
            "user_input": "No, thank you.",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "installment_discount_closing",
                    "dialogue_action": "close_installment_discount_conversation",
                    "response_mode": "empathetic",
                },
            },
        }
    )
    assert "Rohan Gupta" in closing["response"]
    assert closing["conversation_closing"] is True
    assert closing["termination_grace_seconds"] == 3.0


def test_llm_classifies_indirect_post_hold_uncertainty() -> None:
    class OfferResponseLLM:
        @staticmethod
        def generate_json(system_prompt: str, user_prompt: str) -> dict[str, object]:
            del system_prompt, user_prompt
            return {
                "conversation_mode": "hardship_negotiation",
                "negotiation_stage": "evaluating_options",
                "customer_payment_posture": "cannot_pay",
                "discount_stage": "none",
                "hardship_context": {
                    "hardship_detected": True,
                    "hardship_reason": "job_loss",
                    "confidence": 0.96,
                },
                "customer_payment_willingness": 0.45,
                "response_mode": "empathetic",
                "active_dialogue_owner": "plan_proposal",
                "hold_response": "uncertain",
                "discount_response": "none",
                "reason": "Customer doubts recovery after the offered hold.",
            }

    memory = WorkingMemory(
        session_id="hold-response-llm",
        state={
            "identity_verified": True,
            "hardship_hold_stage": "offered",
            "hardship_context": {
                "hardship_detected": True,
                "hardship_reason": "job_loss",
            },
        },
    )
    node = NegotiationClassificationNode(
        llm=OfferResponseLLM(),
        system_prompt="Classify the customer's negotiation response.",
        user_prompt="Customer: {user_input}",
        strict_llm_mode=True,
    )

    update = node.execute(
        {
            "user_input": "Things may still be difficult by then, so I cannot promise I can restart.",
            "memory": memory,
            "identity_verified": True,
        }
    )

    assert update["hold_response"] == "uncertain"
    assert memory.state["hold_response"] == "uncertain"


def test_discount_offer_uses_guarded_llm_wording() -> None:
    class DiscountOfferLLM:
        @staticmethod
        def generate_json(system_prompt: str, user_prompt: str) -> dict[str, str]:
            del system_prompt, user_prompt
            return {
                "message": (
                    "I understand the uncertainty. An approved 10% reduction would bring "
                    "37800.00 down to 34020.00. Would that make the installment more manageable?"
                ),
                "response_target": "customer",
            }

    memory = WorkingMemory(
        session_id="discount-offer-llm",
        state={
            "active_customer_name": "Rohan Gupta",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
            "installment_discount_details": {
                "discount_pct": 10.0,
                "original_amount": 37800.0,
                "revised_amount": 34020.0,
            },
        },
    )
    node = CollectionResponseNode(
        llm=DiscountOfferLLM(),
        strict_llm_mode=False,
        system_prompt="Respond naturally while following the supplied directive.",
        render_user_prompt=(
            "Template: {template_id}\nTone: {tone}\n"
            "Variables: {render_variables_json}\nConstraints: {response_constraints_json}"
        ),
    )

    update = node.execute(
        {
            "user_input": "I do not know if I can resume after the hold.",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "installment_discount_offer",
                    "dialogue_action": "offer_installment_discount",
                    "response_mode": "empathetic",
                },
            },
        }
    )

    assert update["response"].startswith("I understand the uncertainty.")
    assert update["response_render_debug"]["renderer_fallback_used"] is False


def test_discount_plan_tree_moves_offer_to_confirmation() -> None:
    program = {
        "program_id": "JOB_LOSS_INSTALLMENT_DISCOUNT_001",
        "program_type": "installment_discount",
        "eligible_loan_ids": ["LOAN-3002"],
        "hardship_reasons": ["job_loss"],
        "discount_pct": 10,
    }
    memory = WorkingMemory(
        session_id="discount-plan",
        state={
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "active_customer_name": "Rohan Gupta",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
            "conversation_mode": "hardship_negotiation",
            "hardship_context": {
                "hardship_detected": True,
                "hardship_reason": "job_loss",
            },
            "hardship_hold_stage": "offered",
            "discount_stage": "offered",
            "assistance_programs": [program],
            "installment_discount_details": {
                "program_id": program["program_id"],
                "eligible": True,
                "approval_status": "approved",
                "discount_pct": 10.0,
                "discount_amount": 3780.0,
                "revised_amount": 34020.0,
                "review_after_months": 3,
            },
            "active_collection_context": {
                "case": {"loan_id": "LOAN-3002", "product": "personal_loan"}
            },
        },
    )
    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)

    state = {
        "user_input": "I'm not sure I can manage even after 2 months.",
        "memory": memory,
        "steps": 0,
        "discount_stage": "none",
        "discount_offered": False,
    }
    prepared = state_node.execute(state)
    assert prepared["plan_prepared_memory_state"]["discount_stage"] == "offered"
    assert prepared["plan_prepared_memory_state"]["discount_offered"] is True
    graph = graph_node.execute({**state, **prepared})
    directive = directive_node.execute({**state, **prepared, **graph})
    assert directive["plan_proposal"]["conversation_objective"] == "installment_discount_offer"

    memory.set_state(
        discount_stage="confirmed",
        installment_discount_details={
            **memory.state["installment_discount_details"],
            "reference_number": "DISC-A1B2C3D4E5",
            "status": "applied",
            "sms_confirmation": {"status": "sent"},
            "email_confirmation": {"status": "sent"},
        },
    )
    accepted = {"user_input": "Yes, that would make a real difference.", "memory": memory, "steps": 0}
    accepted_prepared = state_node.execute(accepted)
    accepted_graph = graph_node.execute({**accepted, **accepted_prepared})
    accepted_directive = directive_node.execute(
        {**accepted, **accepted_prepared, **accepted_graph}
    )
    assert accepted_graph["conversation_plan"]["current_node_id"] == "confirmation"
    assert (
        accepted_directive["plan_proposal"]["conversation_objective"]
        == "installment_discount_confirmation"
    )


def test_completed_discount_cannot_reopen_on_thank_you() -> None:
    memory = WorkingMemory(
        session_id="discount-closing",
        state={
            "identity_verified": True,
            "discount_stage": "accepted",
            "discount_offered": True,
            "discount_accepted": True,
            "installment_discount_details": {
                "reference_number": "DISC-A1B2C3D4E5",
                "status": "applied",
                "discount_pct": 10.0,
                "revised_amount": 34020.0,
                "sms_confirmation": {"status": "sent"},
                "email_confirmation": {"status": "sent"},
            },
        },
    )
    classifier = NegotiationClassificationNode(llm=None, strict_llm_mode=False)
    classification = classifier.execute(
        {
            "user_input": "sure, thankyou",
            "memory": memory,
            "identity_verified": True,
        }
    )
    assert classification["discount_stage"] == "confirmed"
    assert memory.state["discount_stage"] == "confirmed"

    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)
    state = {
        "user_input": "sure, thankyou",
        "memory": memory,
        "steps": 0,
        **classification,
        "conversation_plan": {
            "plan_id": "plan-COLL-1002",
            "version": 1,
            "status": "active",
            "current_node_id": "close_conversation",
            "nodes": [
                {"id": "confirmation", "label": "Confirm agreed outcome and reference", "status": "done"},
                {"id": "close_conversation", "label": "Close conversation", "status": "in_progress"},
            ],
            "edges": [
                {"from": "confirmation", "to": "close_conversation", "condition": "outcome_confirmed"}
            ],
            "step_markers": {
                "confirmation": {"state": "done"},
                "close_conversation": {"state": "pending"},
            },
        },
    }
    prepared = state_node.execute(state)
    directive = directive_node.execute({**state, **prepared})
    assert (
        directive["plan_proposal"]["conversation_objective"]
        == "installment_discount_closing"
    )
