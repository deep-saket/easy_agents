from __future__ import annotations

import json
from pathlib import Path

from agents.collection_agent.nodes.collection_react_node import CollectionReactNode
from agents.collection_agent.nodes.collection_response_node import CollectionResponseNode
from agents.collection_agent.nodes.plan_proposal_directive_node import PlanProposalDirectiveNode
from agents.collection_agent.nodes.plan_proposal_graph_node import PlanProposalGraphNode
from agents.collection_agent.nodes.plan_proposal_state_node import PlanProposalStateNode
from agents.collection_agent.utils.partial_payment_utils import partial_payment_from_llm_amount
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


def _memory() -> WorkingMemory:
    return WorkingMemory(
        session_id="partial-flow",
        state={
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "active_customer_name": "Rohan Gupta",
            "active_overdue_amount": 37800.0,
            "identity_verified": True,
            "conversation_mode": "collections",
            "customer_payment_posture": "partial_now",
            "active_collection_context": {
                "case": {"case_id": "COLL-1002", "loan_id": "LOAN-3002"},
                "policy": {
                    "allow_partial_payment": True,
                    "min_partial_payment_pct": 20,
                },
            },
        },
    )


def test_llm_normalized_quarter_amount_builds_policy_valid_amount() -> None:
    parsed = partial_payment_from_llm_amount(
        state={
            "customer_payment_capacity": 9450.0,
            "extracted_entities_turn": {"customer_payment_capacity": "9450"},
        },
        memory_state={},
        total_due=37800.0,
    )
    assert parsed == {
        "partial_payment_pct": 25.0,
        "partial_payment_amount": 9450.0,
        "remaining_balance": 28350.0,
    }


def test_llm_extracted_amount_builds_partial_payment_details() -> None:
    parsed = partial_payment_from_llm_amount(
        state={
            "customer_payment_capacity": 9000.0,
            "extracted_entities_turn": {"customer_payment_capacity": "9000"},
        },
        memory_state={},
        total_due=37800.0,
    )
    assert parsed == {
        "partial_payment_pct": 23.81,
        "partial_payment_amount": 9000.0,
        "remaining_balance": 28800.0,
    }


def test_partial_payment_ignores_capacity_not_extracted_in_current_turn() -> None:
    parsed = partial_payment_from_llm_amount(
        state={"extracted_entities_turn": {}},
        memory_state={"customer_payment_capacity": 18900.0},
        total_due=37800.0,
    )
    assert parsed is None


def test_below_minimum_partial_payment_records_validation_reason() -> None:
    memory = _memory()
    memory.set_state(partial_payment_stage="collecting_amount")
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)

    update = directive_node.execute(
        {
            "user_input": "I can pay 7000 today.",
            "memory": memory,
            "steps": 0,
            "identity_verified": True,
            "customer_payment_capacity": 7000.0,
            "extracted_entities_turn": {"customer_payment_capacity": "7000"},
        }
    )

    assert update["plan_proposal"]["conversation_objective"] == "partial_payment_amount_request"
    assert memory.state["partial_payment_stage"] == "collecting_amount"
    validation = memory.state["partial_payment_validation"]
    assert validation["status"] == "rejected"
    assert validation["reason"] == "below_minimum_partial_payment"
    assert validation["offered_amount"] == 7000.0
    assert validation["minimum_partial_payment_pct"] == 20.0
    assert validation["minimum_partial_payment_amount"] == 7560.0


def test_full_amount_is_not_treated_as_partial_payment() -> None:
    parsed = partial_payment_from_llm_amount(
        state={
            "customer_payment_capacity": 37800.0,
            "extracted_entities_turn": {"customer_payment_capacity": "37800"},
        },
        memory_state={},
        total_due=37800.0,
    )
    assert parsed is None


def test_partial_payment_scenario_creates_and_sends_pending_link(tmp_path: Path) -> None:
    memory = _memory()
    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)

    intent_state = {
        "user_input": "I can't pay the full amount but I could manage part of it.",
        "memory": memory,
        "steps": 0,
    }
    prepared = state_node.execute(intent_state)
    graph = graph_node.execute({**intent_state, **prepared})
    directive = directive_node.execute({**intent_state, **prepared, **graph})
    assert directive["plan_proposal"]["conversation_objective"] == "partial_payment_amount_request"
    assert memory.state["partial_payment_stage"] == "collecting_amount"

    amount_state = {
        "user_input": "Maybe about half.",
        "memory": memory,
        "steps": 0,
        "customer_payment_capacity": 18900.0,
        "extracted_entities_turn": {"customer_payment_capacity": "18900"},
    }
    amount_prepared = state_node.execute(amount_state)
    amount_graph = graph_node.execute({**amount_state, **amount_prepared})
    amount_directive = directive_node.execute(
        {**amount_state, **amount_prepared, **amount_graph}
    )
    assert amount_directive["plan_proposal"]["conversation_objective"] == "partial_payment_link_offer"
    assert memory.state["partial_payment_stage"] == "link_offered"
    assert memory.state["partial_payment_details"]["partial_payment_amount"] == 18900.0

    store = _store(tmp_path)
    registry = ToolRegistry()
    registry.register(PaymentLinkCreateTool(store=store))
    registry.register(SMSConfirmationSendTool(store=store))
    react = CollectionReactNode(
        llm=None,
        available_tools=registry.build_catalog(),
        tool_registry=registry,
        max_steps=8,
    )
    executor = ToolExecutionNode(executor=ToolExecutor(registry=registry))
    tool_state = {
        "session_id": "partial-flow",
        "case_id": "COLL-1002",
        "user_id": "CUST-2002",
        "user_input": "Yes please.",
        "memory": memory,
        "steps": 0,
        "observations": [],
    }
    executed: list[str] = []
    for _ in range(2):
        react_update = react.execute(tool_state)
        tool_state.update(react_update)
        executed.append(react_update["decision"].tool_call.tool_name)
        tool_state.update(executor.execute(tool_state))
    final_react = react.execute(tool_state)

    details = memory.state["partial_payment_details"]
    assert executed == ["payment_link_create", "sms_confirmation_send"]
    assert final_react["decision"].done is True
    assert memory.state["partial_payment_stage"] == "confirmed"
    assert memory.state["followup_status"] == "awaiting_partial_payment"
    assert details["payment_reference_id"].startswith("PAY-")
    assert details["sms_confirmation"]["status"] == "sent"
    assert store.load_runtime("payment_links.json")[0]["status"] == "pending"


def test_llm_normalized_quarter_amount_advances_to_link_offer() -> None:
    memory = _memory()
    memory.set_state(partial_payment_stage="collecting_amount")
    state_node = PlanProposalStateNode(llm=None, strict_llm_mode=False)
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    directive_node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)
    state = {
        "user_input": "I can pay a quarter for now.",
        "memory": memory,
        "steps": 0,
        "customer_payment_capacity": 9450.0,
        "extracted_entities_turn": {"customer_payment_capacity": "9450"},
    }

    prepared = state_node.execute(state)
    graph = graph_node.execute({**state, **prepared})
    directive = directive_node.execute({**state, **prepared, **graph})

    assert directive["plan_proposal"]["conversation_objective"] == "partial_payment_link_offer"
    assert memory.state["partial_payment_stage"] == "link_offered"
    assert memory.state["partial_payment_details"] == {
        "original_amount": 37800.0,
        "minimum_partial_payment_pct": 20.0,
            "partial_payment_amount": 9450.0,
            "partial_payment_pct": 25.0,
            "remaining_balance": 28350.0,
        }


def test_partial_payment_link_offer_uses_llm_wording_with_fact_guards() -> None:
    class LinkOfferLLM:
        @staticmethod
        def generate_json(system_prompt: str, user_prompt: str) -> dict[str, str]:
            del system_prompt, user_prompt
            return {
                "message": (
                    "A 9450.00 payment works. That would leave 28350.00 outstanding. "
                    "Would you like me to send the secure link to your registered mobile?"
                ),
                "response_target": "customer",
            }

    memory = _memory()
    memory.set_state(
        partial_payment_stage="link_offered",
        partial_payment_details={
            "partial_payment_amount": 9450.0,
            "partial_payment_pct": 25.0,
            "remaining_balance": 28350.0,
        },
    )
    node = CollectionResponseNode(
        llm=LinkOfferLLM(),
        strict_llm_mode=False,
        system_prompt="Respond naturally while following the supplied directive.",
        render_user_prompt=(
            "Template: {template_id}\nTone: {tone}\n"
            "Variables: {render_variables_json}\nConstraints: {response_constraints_json}"
        ),
    )

    update = node.execute(
        {
            "user_input": "I can pay a quarter for now.",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "partial_payment_link_offer",
                    "dialogue_action": "offer_partial_payment_link",
                    "response_mode": "empathetic",
                },
            },
        }
    )

    assert update["response"].startswith("A 9450.00 payment works.")
    assert update["response_render_debug"]["renderer_fallback_used"] is False


def test_partial_payment_responses_use_amount_balance_and_name() -> None:
    memory = _memory()
    memory.set_state(
        partial_payment_stage="confirmed",
        partial_payment_details={
            "partial_payment_amount": 18900.0,
            "remaining_balance": 18900.0,
            "payment_reference_id": "PAY-A1B2C3D4E5F6",
            "sms_confirmation": {"status": "sent"},
        },
    )
    node = CollectionResponseNode(llm=None, strict_llm_mode=False)
    confirmation = node.execute(
        {
            "user_input": "Yes please.",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "partial_payment_confirmation",
                    "dialogue_action": "confirm_partial_payment_link",
                    "response_mode": "informational",
                },
            },
        }
    )["response"]
    assert "18900.00" in confirmation
    assert "PAY-A1B2C3D4E5F6" in confirmation
    assert "remaining balance is 18900.00" in confirmation
    assert "payment has been received" not in confirmation.lower()
    assert "payment was received" not in confirmation.lower()

    closing = node.execute(
        {
            "user_input": "Thank you",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "partial_payment_closing",
                    "dialogue_action": "close_partial_payment_conversation",
                    "response_mode": "empathetic",
                },
            },
        }
    )
    assert "Rohan Gupta" in closing["response"]
    assert closing["conversation_closing"] is True
    assert closing["termination_grace_seconds"] == 3.0


def test_confirmed_partial_payment_marks_amount_and_link_nodes_done() -> None:
    memory = _memory()
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    initial_state = {
        "user_input": "I can manage part of it.",
        "memory": memory,
        "steps": 0,
    }
    graph_node.execute(initial_state)
    memory.set_state(
        partial_payment_stage="confirmed",
        partial_payment_details={
            "partial_payment_amount": 18900.0,
            "remaining_balance": 18900.0,
            "payment_reference_id": "PAY-A1B2C3D4E5F6",
            "sms_confirmation": {"status": "sent"},
        },
    )

    update = graph_node.execute(
        {
            "user_input": "Yes please.",
            "memory": memory,
            "steps": 0,
        }
    )

    plan = update["conversation_plan"]
    statuses = {
        str(node["id"]): str(node["status"])
        for node in plan["nodes"]
        if str(node.get("id", "")) in {"partial_amount", "partial_link"}
    }
    assert statuses == {
        "partial_amount": "done",
        "partial_link": "done",
    }
    assert plan["step_markers"]["partial_amount"]["state"] == "done"
    assert plan["step_markers"]["partial_link"]["state"] == "done"


def test_confirmation_render_preserves_partial_payment_completion() -> None:
    memory = _memory()
    graph_node = PlanProposalGraphNode(llm=None, strict_llm_mode=False)
    graph_node.execute(
        {
            "user_input": "I can manage part of it.",
            "memory": memory,
            "steps": 0,
        }
    )
    memory.set_state(
        partial_payment_stage="confirmed",
        partial_payment_details={
            "partial_payment_amount": 18900.0,
            "remaining_balance": 18900.0,
            "payment_reference_id": "PAY-A1B2C3D4E5F6",
            "sms_confirmation": {"status": "sent"},
        },
    )
    node = CollectionResponseNode(llm=None, strict_llm_mode=False)

    node.execute(
        {
            "user_input": "Yes please.",
            "memory": memory,
            "plan_proposal": {
                "target": "customer",
                "response_directive": {
                    "conversation_objective": "partial_payment_confirmation",
                    "dialogue_action": "confirm_partial_payment_link",
                    "response_mode": "informational",
                },
            },
        }
    )

    assert "partial_payment_confirmation" in memory.state["completed_objectives"]
    plan = graph_node.execute(
        {
            "user_input": "continue",
            "memory": memory,
            "steps": 0,
        }
    )["conversation_plan"]
    statuses = {
        str(item["id"]): str(item["status"])
        for item in plan["nodes"]
        if str(item.get("id", "")) in {"partial_amount", "partial_link", "confirmation"}
    }
    assert statuses == {
        "partial_amount": "done",
        "partial_link": "done",
        "confirmation": "done",
    }
