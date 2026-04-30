from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.tools.base import BaseTool

from agents.collection_agent.tools.schemas import PlanProposeInput, PlanProposeOutput
from agents.collection_agent.tools.data_store import CollectionDataStore


@dataclass(slots=True)
class PlanProposeTool(BaseTool[PlanProposeInput, PlanProposeOutput]):
    store: CollectionDataStore
    name: str = "plan_propose"
    description: str = "Propose or revise hardship payment plans from local case/policy data."
    input_schema = PlanProposeInput
    output_schema = PlanProposeOutput

    def execute(self, input: PlanProposeInput) -> PlanProposeOutput:
        case_row = self.store.get_case(case_id=input.case_id)
        if case_row is None:
            raise ValueError("Unknown case_id for plan proposal.")
        total_due = float(case_row.get("overdue_amount", 0.0)) + float(case_row.get("late_fee", 0.0))

        months = 6 if input.revision_index == 0 else 12
        monthly = round(total_due / months, 2)
        if input.max_installment_amount is not None and monthly > input.max_installment_amount:
            months = min(36, max(months, int(total_due / max(input.max_installment_amount, 1.0)) + 1))
            monthly = round(total_due / months, 2)

        plan_id = f"PLAN-{uuid4().hex[:10].upper()}"
        due_date = (datetime.now(UTC) + timedelta(days=7)).date().isoformat()
        status = "proposed" if input.revision_index == 0 else "revised"
        rationale = (
            f"Based on hardship='{input.hardship_reason}', total_due={total_due:.2f}, "
            f"revision={input.revision_index}."
        )
        self.store.append_runtime(
            "plan_proposals.json",
            {
                "plan_id": plan_id,
                "case_id": input.case_id,
                "hardship_reason": input.hardship_reason,
                "months": months,
                "monthly_amount": monthly,
                "first_due_date": due_date,
                "rationale": rationale,
                "status": status,
            },
        )
        return PlanProposeOutput(
            plan_id=plan_id,
            case_id=input.case_id,
            hardship_reason=input.hardship_reason,
            months=months,
            monthly_amount=monthly,
            first_due_date=due_date,
            rationale=rationale,
            status=status,
        )
