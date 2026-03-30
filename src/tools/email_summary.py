from __future__ import annotations

from dataclasses import dataclass

from mailmind.core.interfaces import MessageRepository
from mailmind.core.models import MessageBundle
from mailmind.schemas.tools import EmailSummaryInput, EmailSummaryOutput
from tools.base import BaseTool
from tools.helpers import bundle_to_detail


@dataclass(slots=True)
class EmailSummaryTool(BaseTool[EmailSummaryInput, EmailSummaryOutput]):
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
        combined_summary = " | ".join(
            detail.summary.summary or f"{detail.summary.subject} from {detail.summary.from_email}" for detail in details
        )
        return EmailSummaryOutput(summaries=details, combined_summary=combined_summary)
