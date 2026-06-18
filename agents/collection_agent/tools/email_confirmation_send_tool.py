from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from agents.collection_agent.tools.common import utc_now
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.schemas import EmailConfirmationSendInput, EmailConfirmationSendOutput
from src.tools.base import BaseTool


@dataclass(slots=True)
class EmailConfirmationSendTool(BaseTool[EmailConfirmationSendInput, EmailConfirmationSendOutput]):
    store: CollectionDataStore
    name: str = "email_confirmation_send"
    description: str = "Send and record a premium-hold confirmation email."
    input_schema = EmailConfirmationSendInput
    output_schema = EmailConfirmationSendOutput

    def execute(self, input: EmailConfirmationSendInput) -> EmailConfirmationSendOutput:
        customer = self.store.get_customer(input.customer_id) or {}
        recipient = str(customer.get("email", "")).strip()
        if not recipient:
            raise ValueError(f"No email address is available for customer {input.customer_id}.")
        message_id = f"EMAIL-{uuid4().hex[:10].upper()}"
        payload = {
            "message_id": message_id,
            "customer_id": input.customer_id,
            "reference_number": input.reference_number,
            "recipient": recipient,
            "subject": input.subject,
            "message": input.message,
            "status": "sent",
            "sent_at": utc_now().isoformat(),
        }
        self.store.append_runtime("email_confirmations.json", payload)
        return EmailConfirmationSendOutput(**payload)
