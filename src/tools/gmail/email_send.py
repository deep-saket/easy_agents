"""Created: 2026-04-09

Purpose: Implements the email send module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.interfaces.email import EmailSender, MessageRepository
from src.schemas.domain import ReplyDraft
from src.schemas.tool_io import EmailSendInput, EmailSendOutput
from src.tools.base import BaseTool


@dataclass(slots=True)
class EmailSendTool(BaseTool[EmailSendInput, EmailSendOutput]):
    """Sends a saved reply draft or explicit reply for a stored message."""

    sender: EmailSender
    repository: MessageRepository
    name: str = "email_send"
    description: str = "Send a reply email for a stored message."
    input_schema = EmailSendInput
    output_schema = EmailSendOutput

    def execute(self, input: EmailSendInput) -> EmailSendOutput:
        message = self.repository.get_message(input.message_id)
        if message is None:
            raise ValueError(f"Unknown message id: {input.message_id}")
        draft = self.repository.get_draft(input.message_id)
        if draft is None:
            if input.subject is None or input.body_text is None:
                raise ValueError(f"No draft found for message id: {input.message_id}")
            draft = ReplyDraft(message_id=message.id, subject=input.subject, body_text=input.body_text)
        sent = self.sender.send(
            message=message,
            draft=draft,
            recipients=input.recipients or None,
            subject=input.subject,
            body_text=input.body_text,
        )
        return EmailSendOutput(
            status=sent.status,
            message_id=sent.message_id,
            draft_id=sent.draft_id,
            provider_message_id=sent.provider_message_id,
            thread_id=sent.thread_id,
            recipients=sent.recipients,
            subject=sent.subject,
        )


__all__ = ["EmailSendTool"]
