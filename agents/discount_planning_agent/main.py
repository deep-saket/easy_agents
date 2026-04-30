"""CLI entrypoint for discount planning agent demo."""

from __future__ import annotations

import json

from agents.discount_planning_agent.agent import DiscountPlanningAgent


if __name__ == "__main__":
    agent = DiscountPlanningAgent()
    output = agent.run(
        {
            "case_id": "COLL-1001",
            "hardship_reason": "job_loss",
            "target_monthly_emi": 1400.0,
            "reason_for_handoff": "Need optimized concession proposal",
        }
    )
    print(json.dumps(output, indent=2, ensure_ascii=True))
