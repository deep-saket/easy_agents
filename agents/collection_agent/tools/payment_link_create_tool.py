from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from src.tools.base import BaseTool

from agents.collection_agent.tools.common import utc_now
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.schemas import PaymentLinkCreateInput, PaymentLinkCreateOutput


@dataclass(slots=True)
class PaymentLinkCreateTool(BaseTool[PaymentLinkCreateInput, PaymentLinkCreateOutput]):
    store: CollectionDataStore
    name: str = "payment_link_create"
    description: str = "Generate mock signed payment links for local development/demo use."
    input_schema = PaymentLinkCreateInput
    output_schema = PaymentLinkCreateOutput

    def execute(self, input: PaymentLinkCreateInput) -> PaymentLinkCreateOutput:
        ref_id = f"PAY-{uuid4().hex[:12].upper()}"
        expires_at = utc_now() + timedelta(minutes=int(input.expiry_minutes))
        payment_url = f"https://payments.example.local/pay/{ref_id.lower()}"
        self.store.append_runtime(
            "payment_links.json",
            {
                "payment_reference_id": ref_id,
                "case_id": input.case_id,
                "amount": float(input.amount),
                "channel": input.channel,
                "payment_url": payment_url,
                "expires_at": expires_at.isoformat(),
                "status": "pending",
                "created_at": utc_now().isoformat(),
            },
        )
        return PaymentLinkCreateOutput(
            payment_reference_id=ref_id,
            case_id=input.case_id,
            amount=float(input.amount),
            payment_url=payment_url,
            expires_at=expires_at,
        )
