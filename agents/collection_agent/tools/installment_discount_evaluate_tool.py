from __future__ import annotations

from dataclasses import dataclass

from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.schemas import (
    InstallmentDiscountEvaluateInput,
    InstallmentDiscountEvaluateOutput,
)
from src.tools.base import BaseTool


@dataclass(slots=True)
class InstallmentDiscountEvaluateTool(
    BaseTool[InstallmentDiscountEvaluateInput, InstallmentDiscountEvaluateOutput]
):
    store: CollectionDataStore
    name: str = "installment_discount_evaluate"
    description: str = "Evaluate a configured hardship installment-discount program."
    input_schema = InstallmentDiscountEvaluateInput
    output_schema = InstallmentDiscountEvaluateOutput

    def execute(self, input: InstallmentDiscountEvaluateInput) -> InstallmentDiscountEvaluateOutput:
        program = next(
            (
                item
                for item in self.store.load_assistance_programs()
                if str(item.get("program_id", "")).strip() == input.program_id
                and str(item.get("program_type", "")).strip() == "installment_discount"
            ),
            None,
        )
        case = self.store.get_case(case_id=input.case_id)
        eligible_loan_ids = {
            str(item).strip().upper()
            for item in (program or {}).get("eligible_loan_ids", [])
            if str(item).strip()
        }
        case_matches = (
            isinstance(case, dict)
            and str(case.get("customer_id", "")).strip() == input.customer_id
            and (
                not eligible_loan_ids
                or str(case.get("loan_id", "")).strip().upper() in eligible_loan_ids
            )
        )
        eligible = isinstance(program, dict) and case_matches
        discount_pct = float(program.get("discount_pct", 0) or 0) if eligible else 0.0
        requires_approval = bool(program.get("requires_manager_approval", False)) if eligible else False
        approval_status = (
            "approval_required" if eligible and requires_approval
            else "approved" if eligible and discount_pct > 0
            else "not_eligible"
        )
        discount_amount = round(input.original_amount * discount_pct / 100, 2)
        revised_amount = round(input.original_amount - discount_amount, 2)
        return InstallmentDiscountEvaluateOutput(
            case_id=input.case_id,
            customer_id=input.customer_id,
            program_id=input.program_id,
            eligible=eligible and approval_status == "approved",
            approval_status=approval_status,
            discount_pct=discount_pct,
            discount_amount=discount_amount,
            revised_amount=revised_amount,
            review_after_months=int(program.get("review_after_months", 0) or 0) if eligible else 0,
        )
