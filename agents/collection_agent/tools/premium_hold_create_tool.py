from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from agents.collection_agent.tools.common import utc_now
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.schemas import PremiumHoldCreateInput, PremiumHoldCreateOutput
from src.tools.base import BaseTool


def _add_months(value: date, months: int) -> date:
    target_month = value.month - 1 + months
    year = value.year + target_month // 12
    month = target_month % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(slots=True)
class PremiumHoldCreateTool(BaseTool[PremiumHoldCreateInput, PremiumHoldCreateOutput]):
    store: CollectionDataStore
    name: str = "premium_hold_create"
    description: str = "Create and persist an approved premium hold with a unique reference."
    input_schema = PremiumHoldCreateInput
    output_schema = PremiumHoldCreateOutput

    def execute(self, input: PremiumHoldCreateInput) -> PremiumHoldCreateOutput:
        reference_number = f"HOLD-{uuid4().hex[:10].upper()}"
        effective_from = utc_now().date()
        effective_until = _add_months(effective_from, input.hold_months)
        payload = {
            "reference_number": reference_number,
            "case_id": input.case_id,
            "customer_id": input.customer_id,
            "program_id": input.program_id,
            "hold_months": input.hold_months,
            "effective_from": effective_from.isoformat(),
            "effective_until": effective_until.isoformat(),
            "status": "active",
            "created_at": utc_now().isoformat(),
        }
        self.store.append_runtime("premium_holds.json", payload)
        return PremiumHoldCreateOutput(**payload)
