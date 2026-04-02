"""Created: 2026-03-30

Purpose: Implements the email classifier module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.mailmind.core.interfaces import MessageClassifier, MessageRepository
from src.mailmind.core.models import MessageBundle
from src.mailmind.schemas.tools import EmailClassifierInput, EmailClassifierOutput
from src.tools.base import BaseTool
from src.tools.gmail.helpers import bundle_to_summary


@dataclass(slots=True)
class EmailClassifierTool(BaseTool[EmailClassifierInput, EmailClassifierOutput]):
    """Implements the email classifier tool."""
    repository: MessageRepository
    classifier: MessageClassifier
    name: str = "email_classifier"
    description: str = "Classify selected emails and persist the latest classification."
    input_schema = EmailClassifierInput
    output_schema = EmailClassifierOutput

    def execute(self, input: EmailClassifierInput) -> EmailClassifierOutput:
        bundles = []
        for message_id in input.message_ids:
            message = self.repository.get_message(message_id)
            if message is None:
                continue
            result = self.classifier.classify(message)
            self.repository.save_classification(result)
            bundles.append(MessageBundle(message=message, classification=result, draft=None))
        return EmailClassifierOutput(
            classified_count=len(bundles),
            emails=[bundle_to_summary(bundle) for bundle in bundles],
        )
