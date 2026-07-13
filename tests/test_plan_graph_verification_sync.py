from __future__ import annotations

from agents.collection_agent.nodes.plan_proposal_graph_node import PlanProposalGraphNode
from src.memory.types import WorkingMemory


def test_initial_plan_shows_verification_in_progress_before_identity_verified() -> None:
    memory = WorkingMemory(
        session_id="plan-verify-sync",
        state={
            "active_case_id": "COLL-1002",
            "identity_verified": False,
            "right_party_status": "confirmed",
        },
    )

    update = PlanProposalGraphNode().execute({"memory": memory, "user_input": "yes"})
    plan = update["conversation_plan"]
    nodes = {node["id"]: node for node in plan["nodes"]}

    assert plan["current_node_id"] == "verify_identity"
    assert nodes["open_and_context"]["status"] == "done"
    assert nodes["verify_identity"]["status"] == "in_progress"


def test_plan_advances_to_purpose_disclosure_after_identity_verified() -> None:
    memory = WorkingMemory(
        session_id="plan-verify-done-sync",
        state={
            "active_case_id": "COLL-1002",
            "identity_verified": True,
            "right_party_status": "confirmed",
        },
    )

    update = PlanProposalGraphNode().execute(
        {
            "memory": memory,
            "user_input": "My phone number is : 9900001002 and date of birth is 1988-04-22",
        }
    )
    plan = update["conversation_plan"]
    nodes = {node["id"]: node for node in plan["nodes"]}

    assert plan["current_node_id"] == "purpose_disclosure"
    assert nodes["open_and_context"]["status"] == "done"
    assert nodes["verify_identity"]["status"] == "done"
    assert nodes["purpose_disclosure"]["status"] == "in_progress"
