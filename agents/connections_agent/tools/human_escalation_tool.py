from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.tools.base import BaseTool

from agents.connections_agent.tools.common import utc_now
from agents.connections_agent.tools.data_store import ConnectionsDataStore
from agents.connections_agent.tools.schemas import HumanEscalationInput, HumanEscalationOutput


@dataclass(slots=True)
class HumanEscalationTool(BaseTool[HumanEscalationInput, HumanEscalationOutput]):
    store: ConnectionsDataStore
    name: str = "human_escalation"
    description: str = "Escalate sensitive cases to a queue using deterministic routing rules."
    input_schema = HumanEscalationInput
    output_schema = HumanEscalationOutput

    def execute(self, input: HumanEscalationInput) -> HumanEscalationOutput:
        reason = input.reason.lower()
        if any(key in reason for key in ["fraud", "legal", "harassment"]):
            queue = "special_handling"
            priority = "high"
        elif "dispute" in reason:
            queue = "dispute_resolution"
            priority = "medium"
        else:
            queue = "supervisor_review"
            priority = "low"

        escalation_id = f"ESC-{uuid4().hex[:10].upper()}"
        self.store.append_runtime(
            "escalations.json",
            {
                "escalation_id": escalation_id,
                "case_id": input.case_id,
                "reason": input.reason,
                "evidence_summary": input.evidence_summary,
                "queue": queue,
                "priority": priority,
                "status": "queued",
                "created_at": utc_now().isoformat(),
            },
        )
        return HumanEscalationOutput(
            escalation_id=escalation_id,
            case_id=input.case_id,
            queue=queue,
            priority=priority,
            status="queued",
        )
