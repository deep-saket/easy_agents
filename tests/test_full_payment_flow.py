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
from agents.collection_agent.tools.payment_link_create_tool import PaymentLinkCreateTool
from agents.collection_agent.tools.sms_confirmation_send_tool import SMSConfirmationSendTool
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


def _registry(store: CollectionDataStore) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(PaymentLinkCreateTool(store=store))
    registry.register(SMSConfirmationSendTool(store=store))
    return registry


def _memory() -> WorkingMemory:
    return WorkingMemory(
        session_id="full-payment-flow",
        state={
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "active_customer_name": "Rohan Gupta",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
            "right_party_status": "confirmed",
            "conversation_mode": "collections",
            "customer_payment_posture": "negotiating",
            "active_collection_context": {
                "case": {
                    "case_id": "COLL-1002",
                    "loan_id": "LOAN-3002",
                    "overdue_amount": 37800.0,
                },
                "policy": {
                    "allow_partial_payment": True,
                    "min_partial_payment_pct": 20,
                    "max_promise_days": 5,
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


class _WeakAutopayLLM:
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        return {
            "conversation_mode": "collections",
            "negotiation_stage": "none",
            "customer_payment_posture": "unknown",
            "payment_commitment_type": "NONE",
            "payment_option_response": "none",
            "autopay_response": "none",
            "discount_stage": "none",
            "hardship_context": {
                "hardship_detected": False,
                "hardship_reason": None,
                "confidence": 0.0,
            },
            "customer_payment_willingness": 0.5,
            "response_mode": "informational",
            "active_dialogue_owner": "collections",
            "hold_response": "none",
            "discount_response": "none",
            "reason": "default/no strong classification",
        }


def test_scenario_4_pay_in_full_now_creates_link_confirms_and_closes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    registry = _registry(store)
    memory = _memory()
    classifier = NegotiationClassificationNode(llm=None, strict_llm_mode=False)
    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)
    response_node = CollectionResponseNode(llm=None, strict_llm_mode=False)

    pay_now = classifier.execute(
        {
            "user_input": "Oh, I missed that. Yes, I can pay it now.",
            "memory": memory,
            "identity_verified": True,
        }
    )
    assert pay_now["customer_payment_posture"] == "pay_now"
    assert pay_now["payment_commitment_type"] == "FULL_PAYMENT"

    offer_state = {
        "user_input": "Oh, I missed that. Yes, I can pay it now.",
        "memory": memory,
        "steps": 0,
        **pay_now,
    }
    prepared = state_node.execute(offer_state)
    graph = graph_node.execute({**offer_state, **prepared})
    directive = directive_node.execute({**offer_state, **prepared, **graph})
    rendered = response_node.execute(
        {
            **offer_state,
            "plan_proposal": {
                "target": "customer",
                "response_directive": directive["plan_proposal"],
            },
        }
    )
    assert directive["plan_proposal"]["conversation_objective"] == "full_payment_link_offer"
    assert memory.state["payment_resolution_stage"] == "options_offered"
    assert "secure payment link" in rendered["response"].lower()


    assert "guide you" in rendered["response"].lower()

    link_choice = classifier.execute(
        {
            "user_input": "Send me the link, please.",
            "memory": memory,
            "identity_verified": True,
        }
    )
    assert link_choice["payment_option_response"] == "payment_link"
    react = CollectionReactNode(
        llm=None,
        available_tools=registry.build_catalog(),
        tool_registry=registry,
        max_steps=8,
    )
    executor = ToolExecutionNode(executor=ToolExecutor(registry=registry))
    tool_state = {
        "session_id": "full-payment-flow",
        "case_id": "COLL-1002",
        "user_id": "CUST-2002",
        "user_input": "Send me the link, please.",
        "memory": memory,
        "steps": 0,
        "observations": [],
        **link_choice,
    }
    executed: list[str] = []
    for _ in range(2):
        react_update = react.execute(tool_state)
        tool_state.update(react_update)
        executed.append(react_update["decision"].tool_call.tool_name)
        tool_state.update(executor.execute(tool_state))
    final_react = react.execute(tool_state)

    details = memory.state["full_payment_details"]
    assert executed == ["payment_link_create", "sms_confirmation_send"]
    assert final_react["decision"].done is True
    assert memory.state["payment_resolution_stage"] == "confirmed"
    assert memory.state["final_disposition"] == "PAID_IN_FULL"
    assert details["payment_reference_id"].startswith("PAY-")
    assert details["sms_confirmation"]["status"] == "sent"
    assert store.load_runtime("payment_links.json")[0]["amount"] == 37800.0
    assert store.load_runtime("dispositions.json")[0]["disposition_code"] == "PAID_IN_FULL"

    prepared_after_tool = state_node.execute(tool_state)
    graph_after_tool = graph_node.execute({**tool_state, **prepared_after_tool})
    directive_after_tool = directive_node.execute(
        {**tool_state, **prepared_after_tool, **graph_after_tool}
    )
    confirmation = response_node.execute(
        {
            **tool_state,
            "plan_proposal": {
                "target": "customer",
                "response_directive": directive_after_tool["plan_proposal"],
            },
        }
    )
    assert directive_after_tool["plan_proposal"]["conversation_objective"] == "full_payment_confirmation"
    assert details["payment_reference_id"] in confirmation["response"]
    assert "auto-pay" in confirmation["response"]
    assert confirmation["conversation_plan"]["current_node_id"] == "autopay_offer"

    autopay_decline = classifier.execute(
        {
            "user_input": "Maybe later, thanks.",
            "memory": memory,
            "identity_verified": True,
        }
    )
    assert autopay_decline["autopay_response"] == "declined"
    closing_state = {
        "user_input": "Maybe later, thanks.",
        "memory": memory,
        "steps": 0,
        **autopay_decline,
    }
    closing_prepared = state_node.execute(closing_state)
    closing_graph = graph_node.execute({**closing_state, **closing_prepared})
    closing_directive = directive_node.execute(
        {**closing_state, **closing_prepared, **closing_graph}
    )
    closing = response_node.execute(
        {
            **closing_state,
            "plan_proposal": {
                "target": "customer",
                "response_directive": closing_directive["plan_proposal"],
            },
        }
    )
    assert closing_directive["plan_proposal"]["conversation_objective"] == "full_payment_closing"
    assert "Rohan Gupta" in closing["response"]
    assert closing["terminate_call"] is True


def test_autopay_regex_survives_weak_llm_classification() -> None:
    memory = _memory()
    classifier = NegotiationClassificationNode(
        llm=_WeakAutopayLLM(),
        strict_llm_mode=True,
        system_prompt="Classify the negotiation turn.",
        user_prompt="{user_input}",
    )

    classified = classifier.execute(
        {
            "user_input": "Yes, and honestly I keep forgetting these. Is there a way to make it automatic?",
            "memory": memory,
            "identity_verified": True,
        }
    )

    assert classified["payment_commitment_type"] == "FULL_PAYMENT"
    assert classified["payment_option_response"] == "payment_link"
    assert classified["autopay_response"] == "accepted"
    assert classified["autopay_setup_requested"] is True
    assert classified["autopay_stage"] == "requested"


def test_scenario_13_proactive_autopay_request_uses_shared_payment_link(tmp_path: Path) -> None:
    store = _store(tmp_path)
    registry = _registry(store)
    memory = _memory()
    classifier = NegotiationClassificationNode(llm=None, strict_llm_mode=False)
    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)
    response_node = CollectionResponseNode(llm=None, strict_llm_mode=False)

    initial = classifier.execute(
        {
            "user_input": "Yes, and honestly I keep forgetting these. Is there a way to make it automatic?",
            "memory": memory,
            "identity_verified": True,
        }
    )
    assert initial["payment_commitment_type"] == "FULL_PAYMENT"
    assert initial["autopay_response"] == "accepted"
    assert initial["autopay_setup_requested"] is True

    offer_state = {
        "user_input": "Yes, and honestly I keep forgetting these. Is there a way to make it automatic?",
        "memory": memory,
        "steps": 0,
        **initial,
    }
    prepared = state_node.execute(offer_state)
    graph = graph_node.execute({**offer_state, **prepared})
    directive = directive_node.execute({**offer_state, **prepared, **graph})
    rendered = response_node.execute(
        {
            **offer_state,
            "plan_proposal": {
                "target": "customer",
                "response_directive": directive["plan_proposal"],
            },
        }
    )
    assert directive["plan_proposal"]["conversation_objective"] == "full_payment_link_offer"
    assert "same link" in rendered["response"].lower()
    assert "auto-pay" in rendered["response"].lower()

    accepted = classifier.execute(
        {
            "user_input": "That sounds perfect.",
            "memory": memory,
            "identity_verified": True,
        }
    )
    assert accepted["payment_option_response"] == "payment_link"
    assert accepted["autopay_response"] == "accepted"

    react = CollectionReactNode(
        llm=None,
        available_tools=registry.build_catalog(),
        tool_registry=registry,
        max_steps=8,
    )
    executor = ToolExecutionNode(executor=ToolExecutor(registry=registry))
    tool_state = {
        "session_id": "autopay-flow",
        "case_id": "COLL-1002",
        "user_id": "CUST-2002",
        "user_input": "That sounds perfect.",
        "memory": memory,
        "steps": 0,
        "observations": [],
        **accepted,
    }
    executed: list[str] = []
    for _ in range(2):
        react_update = react.execute(tool_state)
        tool_state.update(react_update)
        executed.append(react_update["decision"].tool_call.tool_name)
        tool_state.update(executor.execute(tool_state))
    final_react = react.execute(tool_state)

    assert executed == ["payment_link_create", "sms_confirmation_send"]
    assert final_react["decision"].done is True
    assert memory.state["final_disposition"] == "AUTOPAY_ENABLED"
    assert memory.state["autopay_stage"] == "enabled"
    dispositions = store.load_runtime("dispositions.json")
    assert [row["disposition_code"] for row in dispositions] == ["PAID_IN_FULL", "AUTOPAY_ENABLED"]

    prepared_after_tool = state_node.execute(tool_state)
    graph_after_tool = graph_node.execute({**tool_state, **prepared_after_tool})
    directive_after_tool = directive_node.execute(
        {**tool_state, **prepared_after_tool, **graph_after_tool}
    )
    confirmation = response_node.execute(
        {
            **tool_state,
            "plan_proposal": {
                "target": "customer",
                "response_directive": directive_after_tool["plan_proposal"],
            },
        }
    )
    assert directive_after_tool["plan_proposal"]["conversation_objective"] == "full_payment_confirmation"
    assert "standing instruction" in confirmation["response"].lower()
    assert confirmation["conversation_plan"]["current_node_id"] == "close_conversation"


def test_autopay_acceptance_after_full_payment_offer_records_enabled(tmp_path: Path) -> None:
    store = _store(tmp_path)
    registry = _registry(store)
    memory = _memory()
    memory.set_state(
        payment_commitment_type="FULL_PAYMENT",
        customer_payment_posture="pay_now",
        payment_resolution_stage="autopay_offered",
        full_payment_details={
            "payment_reference_id": "PAY-TEST123",
            "amount": 37800.0,
            "sms_confirmation": {"status": "sent"},
        },
        active_conversation_plan={
            "plan_id": "PLAN-FULL-PAYMENT",
            "version": 1,
            "status": "active",
            "mode": "strict_collections",
            "objective": "Resolve full payment",
            "root_node_id": "open_and_context",
            "current_node_id": "autopay_offer",
            "previous_node_id": "confirmation",
            "next_node_ids": ["close_conversation"],
            "nodes": [
                {"id": "confirmation", "label": "Confirm payment link and reference", "status": "done"},
                {"id": "autopay_offer", "label": "Offer auto-pay setup", "status": "in_progress"},
                {"id": "close_conversation", "label": "Close conversation", "status": "pending"},
            ],
            "edges": [
                {"from": "confirmation", "to": "autopay_offer", "condition": "autopay_offered"},
                {"from": "autopay_offer", "to": "close_conversation", "condition": "autopay_declined_or_later"},
            ],
            "step_markers": {
                "confirmation": {"state": "done"},
                "autopay_offer": {"state": "in_progress"},
                "close_conversation": {"state": "pending"},
            },
            "timeline": [],
            "timeline_snapshots": [],
        },
    )
    classifier = NegotiationClassificationNode(llm=None, strict_llm_mode=False)
    accepted = classifier.execute(
        {
            "user_input": "yes please",
            "memory": memory,
            "identity_verified": True,
        }
    )
    assert accepted["autopay_response"] == "accepted"

    react = CollectionReactNode(
        llm=None,
        available_tools=registry.build_catalog(),
        tool_registry=registry,
        max_steps=8,
    )
    update = react.execute(
        {
            "session_id": "autopay-after-offer",
            "case_id": "COLL-1002",
            "user_id": "CUST-2002",
            "user_input": "yes please",
            "memory": memory,
            "steps": 0,
            "observations": [],
            **accepted,
        }
    )

    assert update["decision"].done is True
    assert memory.state["autopay_stage"] == "enabled"
    assert memory.state["final_disposition"] == "AUTOPAY_ENABLED"
    assert store.load_runtime("dispositions.json")[0]["disposition_code"] == "AUTOPAY_ENABLED"

    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)
    response_node = CollectionResponseNode(llm=None, strict_llm_mode=False)
    confirmation_state = {
        "session_id": "autopay-after-offer",
        "case_id": "COLL-1002",
        "user_id": "CUST-2002",
        "user_input": "yes please",
        "memory": memory,
        "steps": 0,
        "observations": [],
        **accepted,
    }
    prepared = state_node.execute(confirmation_state)
    graph = graph_node.execute({**confirmation_state, **prepared})
    directive = directive_node.execute({**confirmation_state, **prepared, **graph})
    confirmation = response_node.execute(
        {
            **confirmation_state,
            "plan_proposal": {
                "target": "customer",
                "response_directive": directive["plan_proposal"],
            },
        }
    )

    assert directive["plan_proposal"]["conversation_objective"] == "full_payment_confirmation"
    assert "standing instruction" in confirmation["response"].lower()
    synced_plan = memory.state["active_conversation_plan"]
    synced_nodes = {node["id"]: node for node in synced_plan["nodes"]}
    assert synced_plan["current_node_id"] == "close_conversation"
    assert synced_plan["step_markers"]["autopay_offer"]["state"] == "done"
    assert synced_nodes["autopay_offer"]["status"] == "done"
    assert synced_nodes["close_conversation"]["status"] == "in_progress"

    close_state = {
        "session_id": "autopay-after-offer",
        "case_id": "COLL-1002",
        "user_id": "CUST-2002",
        "user_input": "sure",
        "memory": memory,
        "steps": 0,
        "observations": [],
        **accepted,
    }
    close_prepared = state_node.execute(close_state)
    close_graph = graph_node.execute({**close_state, **close_prepared})
    close_directive = directive_node.execute({**close_state, **close_prepared, **close_graph})
    closing = response_node.execute(
        {
            **close_state,
            "plan_proposal": {
                "target": "customer",
                "response_directive": close_directive["plan_proposal"],
            },
        }
    )

    assert close_directive["plan_proposal"]["conversation_objective"] == "full_payment_closing"
    assert "Rohan Gupta" in closing["response"]
    assert closing["conversation_closing"] is True


def test_autopay_enabled_closes_even_when_plan_was_still_on_confirmation() -> None:
    memory = _memory()
    memory.set_state(
        payment_commitment_type="FULL_PAYMENT",
        customer_payment_posture="pay_now",
        payment_resolution_stage="confirmed",
        autopay_setup_requested=True,
        autopay_response="accepted",
        autopay_stage="enabled",
        full_payment_details={
            "payment_reference_id": "PAY-BC5ADF7EA13C",
            "amount": 37800.0,
            "sms_confirmation": {"status": "sent"},
        },
        active_conversation_plan={
            "plan_id": "PLAN-FULL-PAYMENT-STALE",
            "version": 1,
            "status": "active",
            "mode": "strict_collections",
            "objective": "Resolve full payment",
            "root_node_id": "open_and_context",
            "current_node_id": "confirmation",
            "previous_node_id": "full_payment_link",
            "next_node_ids": ["autopay_offer"],
            "nodes": [
                {"id": "full_payment_link", "label": "Create and send secure full-payment link", "status": "done"},
                {"id": "confirmation", "label": "Confirm payment link and reference", "status": "in_progress"},
                {"id": "autopay_offer", "label": "Offer auto-pay setup", "status": "pending"},
                {"id": "close_conversation", "label": "Close conversation", "status": "pending"},
            ],
            "edges": [
                {"from": "full_payment_link", "to": "confirmation", "condition": "link_sent"},
                {"from": "confirmation", "to": "autopay_offer", "condition": "autopay_offered"},
                {"from": "autopay_offer", "to": "close_conversation", "condition": "autopay_declined_or_later"},
            ],
            "step_markers": {
                "full_payment_link": {"state": "done"},
                "confirmation": {"state": "done", "reason": "autopay_enabled_confirmation_delivered"},
                "autopay_offer": {"state": "done"},
                "close_conversation": {"state": "pending"},
            },
            "timeline": [],
            "timeline_snapshots": [],
        },
    )
    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)
    response_node = CollectionResponseNode(llm=None, strict_llm_mode=False)
    state = {
        "session_id": "autopay-stale-confirmation",
        "case_id": "COLL-1002",
        "user_id": "CUST-2002",
        "user_input": "sure",
        "memory": memory,
        "steps": 0,
        "observations": [],
    }

    prepared = state_node.execute(state)
    graph = graph_node.execute({**state, **prepared})
    directive = directive_node.execute({**state, **prepared, **graph})
    closing = response_node.execute(
        {
            **state,
            "plan_proposal": {
                "target": "customer",
                "response_directive": directive["plan_proposal"],
            },
        }
    )

    assert graph["conversation_plan"]["current_node_id"] == "close_conversation"
    assert directive["plan_proposal"]["conversation_objective"] == "full_payment_closing"
    assert "PAY-BC5ADF7EA13C" not in closing["response"]
    assert "Rohan Gupta" in closing["response"]
    assert closing["conversation_closing"] is True
