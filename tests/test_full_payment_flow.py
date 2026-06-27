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
