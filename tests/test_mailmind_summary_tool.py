"""Created: 2026-04-09

Purpose: Verifies MailMind-specific grouped email summarization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agents.mailmind.tools import MailMindSummaryTool
from src.schemas.domain import (
    ActionType,
    Category,
    ClassificationResult,
    EmailMessage,
    SuggestedAction,
)
from src.storage.duckdb_store import DuckDBMessageRepository


def _message(source_id: str, subject: str) -> EmailMessage:
    return EmailMessage(
        source_id=source_id,
        from_email=f"{source_id}@example.com",
        subject=subject,
        body_text=f"Body for {subject}",
        received_at=datetime.now(timezone.utc),
    )


def _classification(
    *,
    message_id: str,
    category: Category,
    summary: str,
    requires_action: bool,
    impact_score: float,
) -> ClassificationResult:
    return ClassificationResult(
        message_id=message_id,
        priority_score=impact_score,
        impact_score=impact_score,
        category=category,
        requires_action=requires_action,
        action_type=ActionType.REPLY if requires_action else ActionType.NONE,
        confidence=0.9,
        reason_codes=["test"],
        reasoning=summary,
        suggested_action=SuggestedAction.NOTIFY_AND_DRAFT if requires_action else SuggestedAction.ARCHIVE,
        summary=summary,
    )


def test_mailmind_summary_tool_groups_emails_by_actionability_and_impact(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind_summary.db")
    repo.init_db()

    action_message = repo.save_message(_message("gmail-1", "Urgent interview follow-up"))
    impact_message = repo.save_message(_message("gmail-2", "Interesting research opportunity"))
    info_message = repo.save_message(_message("gmail-3", "Weekly newsletter"))

    repo.save_classification(
        _classification(
            message_id=action_message.id,
            category=Category.TIME_SENSITIVE_PROFESSIONAL,
            summary="Needs a reply today.",
            requires_action=True,
            impact_score=0.92,
        )
    )
    repo.save_classification(
        _classification(
            message_id=impact_message.id,
            category=Category.STRONG_ML_RESEARCH_JOB,
            summary="High-upside role worth reviewing.",
            requires_action=False,
            impact_score=0.86,
        )
    )
    repo.save_classification(
        _classification(
            message_id=info_message.id,
            category=Category.NEWSLETTER,
            summary="Routine digest.",
            requires_action=False,
            impact_score=0.12,
        )
    )

    tool = MailMindSummaryTool(repository=repo)
    result = tool.execute(tool.input_schema(max_items=10))

    assert result.total == 3
    assert result.action_required.total == 1
    assert result.action_required.summaries[0].summary.subject == "Urgent interview follow-up"
    assert result.high_impact.total == 1
    assert result.high_impact.summaries[0].summary.subject == "Interesting research opportunity"
    assert result.informational.total == 1
    assert result.informational.summaries[0].summary.subject == "Weekly newsletter"
    assert "Needs a reply today." in result.action_required.combined_summary
    assert "High-upside role worth reviewing." in result.high_impact.combined_summary
    assert "Routine digest." in result.informational.combined_summary
