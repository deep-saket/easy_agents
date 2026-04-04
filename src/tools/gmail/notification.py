"""Created: 2026-03-30

Purpose: Implements the notification module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.interfaces.email import ApprovalQueue, MessageRepository, Notifier
from src.schemas.domain import ApprovalStatus, NotificationPayload
from src.schemas.tool_io import NotificationInput, NotificationOutput
from src.tools.base import BaseTool


@dataclass(slots=True)
class NotificationTool(BaseTool[NotificationInput, NotificationOutput]):
    """Implements the notification tool."""
    notifier: Notifier
    repository: MessageRepository
    approval_queue: ApprovalQueue | None = None
    name: str = "notification"
    description: str = "Execute or inspect approved WhatsApp notification actions."
    input_schema = NotificationInput
    output_schema = NotificationOutput

    def execute(self, input: NotificationInput) -> NotificationOutput:
        if input.approval_id is None:
            raise ValueError("approval_id is required for v1 notification execution.")
        item = self._get_approval(input.approval_id)
        if item is None:
            raise ValueError(f"Unknown approval id: {input.approval_id}")
        payload = NotificationPayload.model_validate(item.payload)
        attempt = self.notifier.send(payload)
        self.repository.save_notification_attempt(attempt)
        updated_status = ApprovalStatus.FAILED if attempt.error else ApprovalStatus.EXECUTED
        if self.approval_queue is not None:
            updated = (
                self.approval_queue.mark_failed(item.id, attempt.error or "notification_failed")
                if attempt.error
                else self.approval_queue.mark_executed(item.id)
            )
            return NotificationOutput(status=updated.status.value, approval_id=updated.id, message_id=updated.target_id)
        updated = item.model_copy(update={"status": updated_status})
        self.repository.update_approval(updated)
        return NotificationOutput(status=updated.status.value, approval_id=updated.id, message_id=updated.target_id)

    def _get_approval(self, approval_id: str):
        if self.approval_queue is not None:
            item = self.approval_queue.get(approval_id)
            if item is not None:
                return item
        return self.repository.get_approval(approval_id)
