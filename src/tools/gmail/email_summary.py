"""Created: 2026-03-30

Purpose: Implements the email summary module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.interfaces.email import MessageRepository
from src.schemas.domain import MessageBundle
from src.schemas.tool_io import EmailSummaryInput, EmailSummaryOutput
from src.tools.base import BaseTool
from src.tools.gmail.helpers import bundle_to_detail


@dataclass(slots=True)
class EmailSummaryTool(BaseTool[EmailSummaryInput, EmailSummaryOutput]):
    """Implements the email summary tool."""
    repository: MessageRepository
    name: str = "email_summary"
    description: str = "Summarize selected stored emails."
    input_schema = EmailSummaryInput
    output_schema = EmailSummaryOutput

    def execute(self, input: EmailSummaryInput) -> EmailSummaryOutput:
        bundles = []
        for message_id in input.message_ids[: input.max_items]:
            message = self.repository.get_message(message_id)
            if message is None:
                continue
            classification = self.repository.get_latest_classification(message_id)
            bundles.append(MessageBundle(message=message, classification=classification, draft=None))
        details = [bundle_to_detail(bundle) for bundle in bundles]
        categories: dict[str, int] = {}
        for detail in details:
            label = detail.summary.category or "unclassified"
            categories[label] = categories.get(label, 0) + 1
        combined_summary = " | ".join(
            detail.summary.summary or f"{detail.summary.subject} from {detail.summary.from_email}" for detail in details
        )
        return EmailSummaryOutput(
            total=len(details),
            categories=categories,
            summaries=details,
            combined_summary=combined_summary,
        )
