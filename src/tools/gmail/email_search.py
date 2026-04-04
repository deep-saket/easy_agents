"""Created: 2026-03-30

Purpose: Implements the email search module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.interfaces.email import MessageRepository
from src.schemas.tool_io import EmailSearchInput, EmailSearchOutput
from src.tools.base import BaseTool
from src.tools.gmail.helpers import bundle_to_summary


@dataclass(slots=True)
class EmailSearchTool(BaseTool[EmailSearchInput, EmailSearchOutput]):
    """Implements the email search tool."""
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
        summaries = [bundle_to_summary(bundle) for bundle in bundles]
        categories: dict[str, int] = {}
        for summary in summaries:
            label = summary.category or "unclassified"
            categories[label] = categories.get(label, 0) + 1
        return EmailSearchOutput(total=len(summaries), categories=categories, emails=summaries)
