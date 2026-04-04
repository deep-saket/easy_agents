"""Created: 2026-03-30

Purpose: Implements the gmail fetch module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.interfaces.email import EmailSource, MessageClassifier, MessageRepository
from src.schemas.domain import MessageBundle
from src.schemas.tool_io import GmailFetchInput, GmailFetchOutput
from src.tools.base import BaseTool
from src.tools.gmail.helpers import bundle_to_summary, message_to_summary


@dataclass(slots=True)
class GmailFetchTool(BaseTool[GmailFetchInput, GmailFetchOutput]):
    """Implements the gmail fetch tool."""
    source: EmailSource
    repository: MessageRepository | None = None
    classifier: MessageClassifier | None = None
    name: str = "gmail_fetch"
    description: str = "Fetch and optionally process new Gmail messages."
    input_schema = GmailFetchInput
    output_schema = GmailFetchOutput

    def execute(self, input: GmailFetchInput) -> GmailFetchOutput:
        messages = self.source.fetch_new_messages()
        if not input.process_messages:
            return GmailFetchOutput(
                fetched_count=len(messages),
                processed_count=0,
                emails=[message_to_summary(message) for message in messages],
            )
        if self.repository is None:
            raise ValueError("GmailFetchTool requires a repository when `process_messages=True`.")
        bundles: list[MessageBundle] = []
        for message in messages:
            if self.repository.has_message(message.source_id):
                continue
            stored = self.repository.save_message(message)
            classification = None
            if self.classifier is not None:
                classification = self.classifier.classify(stored)
                self.repository.save_classification(classification)
            bundles.append(MessageBundle(message=stored, classification=classification, draft=None))
        return GmailFetchOutput(
            fetched_count=len(messages),
            processed_count=len(bundles),
            emails=[bundle_to_summary(bundle) for bundle in bundles],
        )
