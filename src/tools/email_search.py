from __future__ import annotations

from dataclasses import dataclass

from mailmind.core.interfaces import MessageRepository
from mailmind.schemas.tools import EmailSearchInput, EmailSearchOutput
from tools.base import BaseTool
from tools.helpers import bundle_to_summary


@dataclass(slots=True)
class EmailSearchTool(BaseTool[EmailSearchInput, EmailSearchOutput]):
    repository: MessageRepository
    name: str = "email_search"
    description: str = "Search stored emails by keyword, category, sender, and time range."
    input_schema = EmailSearchInput
    output_schema = EmailSearchOutput

    def execute(self, input: EmailSearchInput) -> EmailSearchOutput:
        bundles = self.repository.search_messages(
            query=input.query,
            category=input.category,
            date_from=input.date_from,
            date_to=input.date_to,
            sender=input.sender,
            limit=input.limit,
            only_important=input.only_important,
        )
        return EmailSearchOutput(emails=[bundle_to_summary(bundle) for bundle in bundles])
