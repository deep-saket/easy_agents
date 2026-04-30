from __future__ import annotations

from dataclasses import dataclass

from src.tools.base import BaseTool

from agents.connections_agent.tools.data_store import ConnectionsDataStore
from agents.connections_agent.tools.schemas import OfferEligibilityInput, OfferEligibilityOutput


@dataclass(slots=True)
class OfferEligibilityTool(BaseTool[OfferEligibilityInput, OfferEligibilityOutput]):
    store: ConnectionsDataStore
    name: str = "offer_eligibility"
    description: str = "Evaluate offer eligibility with deterministic local policy rules."
    input_schema = OfferEligibilityInput
    output_schema = OfferEligibilityOutput

    def execute(self, input: OfferEligibilityInput) -> OfferEligibilityOutput:
        case_row = self.store.get_case(case_id=input.case_id)
        if case_row is None:
            raise ValueError("Unknown case for offer eligibility.")
        policy = self.store.get_policy(str(case_row.get("loan_id")))
        if policy is None:
            raise ValueError("Missing policy for case loan.")

        dpd = int(case_row.get("dpd", 0))
        max_waiver_pct = float(policy.get("max_waiver_pct", 0.0))
        waiver_allowed = bool(policy.get("waiver_allowed", False))
        restructure_allowed = bool(policy.get("restructure_allowed", False))

        reason_codes: list[str] = []
        approved_waiver = 0.0
        offer_type: str = "none"
        allowed = False

        if waiver_allowed and input.hardship_flag and dpd <= 60:
            requested = float(input.requested_waiver_pct or max_waiver_pct)
            approved_waiver = min(max_waiver_pct, max(requested, 0.0))
            offer_type = "waiver"
            allowed = approved_waiver > 0
            reason_codes.append("hardship_waiver_rule")
        elif restructure_allowed and dpd > 60:
            offer_type = "restructure"
            allowed = True
            reason_codes.append("high_dpd_restructure_rule")
        else:
            reason_codes.append("no_policy_match")

        recommended_next = "capture_promise" if not allowed else "present_offer"
        return OfferEligibilityOutput(
            case_id=input.case_id,
            allowed=allowed,
            offer_type=offer_type,
            approved_waiver_pct=round(approved_waiver, 2),
            reason_codes=reason_codes,
            recommended_next=recommended_next,
        )
