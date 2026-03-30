from __future__ import annotations

from dataclasses import dataclass

from mailmind.core.interfaces import EmailSource
from mailmind.core.orchestrator import MailOrchestrator
from mailmind.schemas.tools import GmailFetchInput, GmailFetchOutput
from mailmind.tools.base import BaseTool
from mailmind.tools.helpers import bundle_to_summary


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

