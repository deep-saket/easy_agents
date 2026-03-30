from __future__ import annotations

from dataclasses import dataclass

from mailmind.core.orchestrator import MailOrchestrator
from mailmind.schemas.tools import NotificationInput, NotificationOutput
from tools.base import BaseTool


@dataclass(slots=True)
class NotificationTool(BaseTool[NotificationInput, NotificationOutput]):
    orchestrator: MailOrchestrator
    name: str = "notification"
    description: str = "Execute or inspect approved WhatsApp notification actions."
    input_schema = NotificationInput
    output_schema = NotificationOutput

    def execute(self, input: NotificationInput) -> NotificationOutput:
        if input.approval_id is None:
            raise ValueError("approval_id is required for v1 notification execution.")
        item = self.orchestrator.execute_approval(input.approval_id)
        return NotificationOutput(status=item.status.value, approval_id=item.id, message_id=item.target_id)
