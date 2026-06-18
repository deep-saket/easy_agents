from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from agents.collection_agent.tools.common import utc_now
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.schemas import SMSConfirmationSendInput, SMSConfirmationSendOutput
from src.tools.base import BaseTool


@dataclass(slots=True)
class SMSConfirmationSendTool(BaseTool[SMSConfirmationSendInput, SMSConfirmationSendOutput]):
    store: CollectionDataStore
    name: str = "sms_confirmation_send"
    description: str = "Send and record a premium-hold confirmation SMS."
    input_schema = SMSConfirmationSendInput
    output_schema = SMSConfirmationSendOutput

    def execute(self, input: SMSConfirmationSendInput) -> SMSConfirmationSendOutput:
        customer = self.store.get_customer(input.customer_id) or {}
        recipient = str(customer.get("phone", "")).strip()
        if not recipient:
            raise ValueError(f"No SMS number is available for customer {input.customer_id}.")
        message_id = f"SMS-{uuid4().hex[:10].upper()}"
        payload = {
            "message_id": message_id,
            "customer_id": input.customer_id,
            "reference_number": input.reference_number,
            "recipient": recipient,
            "message": input.message,
            "status": "sent",
            "sent_at": utc_now().isoformat(),
        }
        self.store.append_runtime("sms_confirmations.json", payload)
        return SMSConfirmationSendOutput(**payload)
