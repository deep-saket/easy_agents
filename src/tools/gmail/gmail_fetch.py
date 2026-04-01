"""Created: 2026-03-30

Purpose: Implements the gmail fetch module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.mailmind.core.interfaces import EmailSource
from src.mailmind.core.orchestrator import MailOrchestrator
from src.mailmind.schemas.tools import GmailFetchInput, GmailFetchOutput
from src.tools.base import BaseTool
from src.tools.gmail.helpers import bundle_to_summary


@dataclass(slots=True)
class GmailFetchTool(BaseTool[GmailFetchInput, GmailFetchOutput]):
    source: EmailSource
    orchestrator: MailOrchestrator
    name: str = "gmail_fetch"
    description: str = "Fetch and optionally process new Gmail messages."
    input_schema = GmailFetchInput
    output_schema = GmailFetchOutput

    def execute(self, input: GmailFetchInput) -> GmailFetchOutput:
        messages = self.source.fetch_new_messages()
        bundles = self.orchestrator.process_messages(messages) if input.process_messages else []
        return GmailFetchOutput(
            fetched_count=len(messages),
            processed_count=len(bundles),
            emails=[bundle_to_summary(bundle) for bundle in bundles],
        )
