from __future__ import annotations

from pathlib import Path

from agents.collection_agent.nodes.collection_react_node import CollectionReactNode
from agents.collection_agent.nodes.pre_plan_intent_node import PrePlanIntentNode
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.email_confirmation_send_tool import EmailConfirmationSendTool
from agents.collection_agent.tools.premium_hold_create_tool import PremiumHoldCreateTool
from agents.collection_agent.tools.schemas import (
    EmailConfirmationSendInput,
    PremiumHoldCreateInput,
    SMSConfirmationSendInput,
)
from agents.collection_agent.tools.sms_confirmation_send_tool import SMSConfirmationSendTool
from src.memory.types import WorkingMemory
from src.nodes.tool_execution_node import ToolExecutionNode
from src.tools.executor import ToolExecutor
from src.tools.registry import ToolRegistry


def _store(tmp_path: Path) -> CollectionDataStore:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "customers.json").write_text(
        """
[
  {
    "customer_id": "CUST-2002",
    "phone": "+919900001002",
    "email": "rohan.gupta@example.com"
  }
]
""".strip(),
        encoding="utf-8",
    )
    return CollectionDataStore(base_dir=tmp_path)


def test_hold_creation_and_confirmations_are_persisted(tmp_path: Path) -> None:
    store = _store(tmp_path)
    hold = PremiumHoldCreateTool(store=store).execute(
        PremiumHoldCreateInput(
            case_id="COLL-1002",
            customer_id="CUST-2002",
            program_id="PREMIUM_HOLD_001",
            hold_months=2,
        )
    )

    message = f"Your premium hold reference is {hold.reference_number}."
    sms = SMSConfirmationSendTool(store=store).execute(
        SMSConfirmationSendInput(
            customer_id="CUST-2002",
            reference_number=hold.reference_number,
            message=message,
        )
    )
    email = EmailConfirmationSendTool(store=store).execute(
        EmailConfirmationSendInput(
            customer_id="CUST-2002",
            reference_number=hold.reference_number,
            subject="Premium hold confirmation",
            message=message,
        )
    )

    assert hold.reference_number.startswith("HOLD-")
    assert hold.reference_number != "COLL-1002"
    assert hold.status == "active"
    assert sms.status == "sent"
    assert email.status == "sent"
    assert store.load_runtime("premium_holds.json")[0]["reference_number"] == hold.reference_number
    assert store.load_runtime("sms_confirmations.json")[0]["reference_number"] == hold.reference_number
    assert store.load_runtime("email_confirmations.json")[0]["reference_number"] == hold.reference_number


def test_accepted_hold_routes_through_all_three_tools(tmp_path: Path) -> None:
    store = _store(tmp_path)
    registry = ToolRegistry()
    registry.register(PremiumHoldCreateTool(store=store))
    registry.register(SMSConfirmationSendTool(store=store))
    registry.register(EmailConfirmationSendTool(store=store))
    react = CollectionReactNode(
        llm=None,
        available_tools=registry.build_catalog(),
        tool_registry=registry,
        max_steps=8,
    )
    tool_execution = ToolExecutionNode(executor=ToolExecutor(registry=registry))
    memory = WorkingMemory(
        session_id="hold-tool-chain",
        state={
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "hardship_hold_stage": "offered",
            "hardship_hold_program": {
                "program_id": "PREMIUM_HOLD_001",
                "max_hold_months": 2,
            },
        },
    )
    state = {
        "session_id": "hold-tool-chain",
        "case_id": "COLL-1002",
        "user_id": "CUST-2002",
        "user_input": "Yes, that would really help",
        "memory": memory,
        "steps": 0,
        "observations": [],
    }

    executed: list[str] = []
    for _ in range(3):
        react_update = react.execute(state)
        state.update(react_update)
        tool_name = react_update["decision"].tool_call.tool_name
        executed.append(tool_name)
        tool_update = tool_execution.execute(state)
        state.update(tool_update)

    final_react_update = react.execute(state)
    state.update(final_react_update)

    details = memory.state["hardship_hold_details"]
    assert executed == [
        "premium_hold_create",
        "sms_confirmation_send",
        "email_confirmation_send",
    ]
    assert final_react_update["decision"].done is True
    assert memory.state["hardship_hold_stage"] == "confirmed"
    assert details["reference_number"].startswith("HOLD-")
    assert details["sms_confirmation"]["status"] == "sent"
    assert details["email_confirmation"]["status"] == "sent"


def test_pre_plan_routes_accepted_hold_to_decision_path() -> None:
    memory = WorkingMemory(
        session_id="hold-pre-plan",
        state={
            "identity_verified": True,
            "hardship_hold_stage": "offered",
        },
    )
    node = PrePlanIntentNode(
        llm=None,
        allow_deterministic_fallback=True,
        system_prompt="",
        user_prompt="",
    )

    update = node.execute(
        {
            "user_input": "Yes, that would really help",
            "memory": memory,
            "identity_verified": True,
        }
    )

    assert update["pre_plan_intent"]["intent"] == "decide"
    assert node.route(update) == "decide"
