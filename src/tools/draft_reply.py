"""Created: 2026-03-30

Purpose: Implements the draft reply module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from mailmind.core.interfaces import DraftGenerator, MessageRepository
from mailmind.schemas.tools import DraftReplyInput, DraftReplyOutput
from tools.base import BaseTool


@dataclass(slots=True)
class DraftReplyTool(BaseTool[DraftReplyInput, DraftReplyOutput]):
    repository: MessageRepository
    drafter: DraftGenerator
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
        draft = self.drafter.generate(message, classification)
        self.repository.save_draft(draft)
        return DraftReplyOutput(
            draft_id=draft.id,
            message_id=draft.message_id,
            subject=draft.subject,
            body_text=draft.body_text,
        )
