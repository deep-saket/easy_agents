from __future__ import annotations

from dataclasses import dataclass

from src.tools.base import BaseTool

from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.schemas import LoanPolicyLookupInput, LoanPolicyLookupOutput


@dataclass(slots=True)
class LoanPolicyLookupTool(BaseTool[LoanPolicyLookupInput, LoanPolicyLookupOutput]):
    store: CollectionDataStore
    name: str = "loan_policy_lookup"
    description: str = "Lookup loan policy constraints from local fixture data."
    input_schema = LoanPolicyLookupInput
    output_schema = LoanPolicyLookupOutput

    def execute(self, input: LoanPolicyLookupInput) -> LoanPolicyLookupOutput:
        loan_id = input.loan_id
        if loan_id is None and input.case_id is not None:
            case_row = self.store.get_case(case_id=input.case_id)
            if case_row is None:
                raise ValueError("Unknown case id for policy lookup.")
            loan_id = str(case_row.get("loan_id"))
        if loan_id is None:
            raise ValueError("loan_id or case_id is required.")

        policy = self.store.get_policy(loan_id)
        if policy is None:
            raise ValueError(f"No policy found for loan_id={loan_id}")

        return LoanPolicyLookupOutput(
            loan_id=loan_id,
            product=str(policy.get("product", "loan")),
            max_promise_days=int(policy.get("max_promise_days", 7)),
            waiver_allowed=bool(policy.get("waiver_allowed", False)),
            max_waiver_pct=float(policy.get("max_waiver_pct", 0.0)),
            restructure_allowed=bool(policy.get("restructure_allowed", False)),
            notes=str(policy.get("notes", "")),
        )
