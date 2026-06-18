from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from agents.collection_agent.tools.common import utc_now
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.schemas import (
    InstallmentDiscountApplyInput,
    InstallmentDiscountApplyOutput,
)
from src.tools.base import BaseTool


@dataclass(slots=True)
class InstallmentDiscountApplyTool(
    BaseTool[InstallmentDiscountApplyInput, InstallmentDiscountApplyOutput]
):
    store: CollectionDataStore
    name: str = "installment_discount_apply"
    description: str = "Apply and persist an approved installment discount."
    input_schema = InstallmentDiscountApplyInput
    output_schema = InstallmentDiscountApplyOutput

    def execute(self, input: InstallmentDiscountApplyInput) -> InstallmentDiscountApplyOutput:
        discount_amount = round(input.original_amount * input.discount_pct / 100, 2)
        expected_revised = round(input.original_amount - discount_amount, 2)
        if abs(expected_revised - input.revised_amount) > 0.01:
            raise ValueError("Revised amount does not match the approved discount.")
        payload = {
            "reference_number": f"DISC-{uuid4().hex[:10].upper()}",
            "case_id": input.case_id,
            "customer_id": input.customer_id,
            "program_id": input.program_id,
            "original_amount": round(input.original_amount, 2),
            "discount_pct": round(input.discount_pct, 2),
            "discount_amount": discount_amount,
            "revised_amount": expected_revised,
            "status": "applied",
            "applied_at": utc_now().isoformat(),
        }
        self.store.append_runtime("installment_discounts.json", payload)
        return InstallmentDiscountApplyOutput(**payload)
