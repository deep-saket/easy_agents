"""Created: 2026-04-09

Purpose: Implements the MailMind-specific grouped email summary tool.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from src.interfaces.email import MessageRepository
from src.schemas.domain import MessageBundle
from src.schemas.emails import EmailDetail
from src.tools.base import BaseTool
from src.tools.gmail.helpers import bundle_to_detail


class MailMindEmailSummaryInput(BaseModel):
    """Represents input for MailMind grouped email summaries."""

    message_ids: list[str] = Field(default_factory=list)
    max_items: int = 10
    high_impact_threshold: float = 0.75


class MailMindSummarySection(BaseModel):
    """Represents one MailMind summary group."""

    title: str
    total: int
    summaries: list[EmailDetail] = Field(default_factory=list)
    combined_summary: str = ""


class MailMindEmailSummaryOutput(BaseModel):
    """Represents grouped MailMind summary output."""

    total: int
    action_required: MailMindSummarySection
    high_impact: MailMindSummarySection
    informational: MailMindSummarySection


@dataclass(slots=True)
class MailMindSummaryTool(BaseTool[MailMindEmailSummaryInput, MailMindEmailSummaryOutput]):
    """Builds MailMind-specific grouped email summaries."""

    repository: MessageRepository
    name: str = "mailmind_email_summary"
    description: str = "Summarize emails into MailMind groups: Action Required, High Impact, and Informational."
    input_schema = MailMindEmailSummaryInput
    output_schema = MailMindEmailSummaryOutput

    def execute(self, input: MailMindEmailSummaryInput) -> MailMindEmailSummaryOutput:
        bundles = self._select_bundles(input)
        action_required: list[EmailDetail] = []
        high_impact: list[EmailDetail] = []
        informational: list[EmailDetail] = []

        for bundle in bundles:
            detail = bundle_to_detail(bundle)
            classification = bundle.classification
            if classification is not None and classification.requires_action:
                action_required.append(detail)
            elif classification is not None and classification.impact_score >= input.high_impact_threshold:
                high_impact.append(detail)
            else:
                informational.append(detail)

        return MailMindEmailSummaryOutput(
            total=len(bundles),
            action_required=self._build_section("Action Required", action_required),
            high_impact=self._build_section("High Impact", high_impact),
            informational=self._build_section("Informational", informational),
        )

    def _select_bundles(self, input: MailMindEmailSummaryInput) -> list[MessageBundle]:
        bundles: list[MessageBundle] = []
        message_ids = input.message_ids[: input.max_items]
        if message_ids:
            for message_id in message_ids:
                message = self.repository.get_message(message_id)
                if message is None:
                    continue
                bundles.append(
                    MessageBundle(
                        message=message,
                        classification=self.repository.get_latest_classification(message_id),
                        draft=None,
                    )
                )
            return bundles
        return self.repository.list_messages()[: input.max_items]

    @staticmethod
    def _build_section(title: str, summaries: list[EmailDetail]) -> MailMindSummarySection:
        combined_summary = " | ".join(
            detail.summary.summary or f"{detail.summary.subject} from {detail.summary.from_email}" for detail in summaries
        )
        return MailMindSummarySection(
            title=title,
            total=len(summaries),
            summaries=summaries,
            combined_summary=combined_summary,
        )
