"""Created: 2026-03-30

Purpose: Implements the draft reply module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.interfaces.email import DraftGenerator, MessageRepository
from src.schemas.domain import ClassificationResult, EmailMessage, ReplyDraft
from src.schemas.tool_io import DraftReplyInput, DraftReplyOutput
from src.tools.base import BaseTool


@dataclass(slots=True)
class SimpleDraftGenerator(DraftGenerator):
    """Provides a minimal built-in reply draft generator for email tools."""

    def generate(self, message: EmailMessage, classification: ClassificationResult) -> ReplyDraft:
        greeting = f"Hi {message.from_name}," if message.from_name else "Hi,"
        subject = message.subject if message.subject.lower().startswith("re:") else f"Re: {message.subject}"
        body = (
            f"{greeting}\n\n"
            f"Thank you for your email about \"{message.subject}\".\n"
            f"I reviewed the details and will follow up shortly.\n\n"
            f"Context noted: {classification.summary}\n\n"
            "Best,\n"
            "Saket"
        )
        return ReplyDraft(message_id=message.id, subject=subject, body_text=body)


@dataclass(slots=True)
class DraftReplyTool(BaseTool[DraftReplyInput, DraftReplyOutput]):
    """Implements the draft reply tool."""
    repository: MessageRepository
    drafter: DraftGenerator | None = None
    name: str = "draft_reply"
    description: str = "Generate a reply draft for a stored email."
    input_schema = DraftReplyInput
    output_schema = DraftReplyOutput

    def execute(self, input: DraftReplyInput) -> DraftReplyOutput:
        message = self.repository.get_message(input.message_id)
        if message is None:
            raise ValueError(f"Unknown message id: {input.message_id}")
        classification = self.repository.get_latest_classification(input.message_id)
        if classification is None:
            raise ValueError(f"No classification found for message id: {input.message_id}")
        draft = (self.drafter or SimpleDraftGenerator()).generate(message, classification)
        self.repository.save_draft(draft)
        return DraftReplyOutput(
            draft_id=draft.id,
            message_id=draft.message_id,
            subject=draft.subject,
            body_text=draft.body_text,
        )
