"""Discount planning specialist agent (standalone)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class DiscountPlanningAgent:
    """Returns policy-aware discount planning recommendations.

    This is intentionally small for demo use. It is called by collection_agent
    through a handoff tool and returns only agent-to-agent payload.
    """

    llm: Any | None = None

    def run(self, handoff_payload: dict[str, Any]) -> dict[str, Any]:
        case_id = str(handoff_payload.get("case_id", "UNKNOWN"))
        hardship_reason = str(handoff_payload.get("hardship_reason", "income_reduction"))
        target_emi = handoff_payload.get("target_monthly_emi")

        if isinstance(target_emi, (int, float)) and float(target_emi) > 0:
            monthly_emi = round(float(target_emi), 2)
            tenure = 24
        else:
            monthly_emi = 1500.0
            tenure = 18

        recommended_offer = {
            "case_id": case_id,
            "offer_type": "restructure",
            "waiver_pct": 0.0,
            "tenure_months": tenure,
            "monthly_emi": monthly_emi,
            "hardship_reason": hardship_reason,
        }
        return {
            "recommended_offer": recommended_offer,
            "offer_variants": [
                {**recommended_offer, "tenure_months": tenure + 6, "monthly_emi": round(monthly_emi * 0.85, 2)},
                {**recommended_offer, "tenure_months": max(12, tenure - 6), "monthly_emi": round(monthly_emi * 1.2, 2)},
            ],
            "rationale": "Selected baseline restructure from hardship reason and requested EMI target.",
            "compliance_flags": ["demo_policy_check_pending"],
            "confidence": 0.62,
            "next_action_hint": "Present recommended_offer first, then use offer_variants if rejected.",
        }
