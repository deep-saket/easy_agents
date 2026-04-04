"""Created: 2026-04-04

Purpose: Tests Gmail-oriented tools using direct framework dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.interfaces.email import Notifier
from src.schemas.domain import (
    ApprovalItem,
    ApprovalKind,
    ApprovalStatus,
    Category,
    ClassificationResult,
    EmailMessage,
    NotificationAttempt,
    NotificationStatus,
    SuggestedAction,
)
from src.storage.duckdb_store import DuckDBMessageRepository
from src.tools.gmail.gmail_fetch import GmailFetchTool
from src.tools.gmail.notification import NotificationTool


class _StaticEmailSource:
    def __init__(self, messages: list[EmailMessage]) -> None:
        self._messages = messages

    def fetch_new_messages(self) -> list[EmailMessage]:
        return list(self._messages)


class _Classifier:
    def classify(self, message: EmailMessage) -> ClassificationResult:
        return ClassificationResult(
            message_id=message.id,
            priority_score=0.91,
            category=Category.STRONG_ML_RESEARCH_JOB,
            confidence=0.88,
            reason_codes=["keyword_match"],
            suggested_action=SuggestedAction.NOTIFY_AND_DRAFT,
            summary="High-value research opportunity.",
        )


class _Notifier(Notifier):
    def send(self, payload):
        return NotificationAttempt(
            message_id=payload.message_id,
            channel=payload.channel,
            destination=payload.destination,
            payload=payload.model_dump(mode="json"),
            status=NotificationStatus.SENT,
        )


def test_gmail_fetch_tool_saves_and_classifies_messages(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    message = EmailMessage(
        source_id="gmail-1",
        from_email="talent@deepmind.com",
        subject="Research role",
        body_text="We are hiring.",
        received_at=datetime.now(timezone.utc),
    )
    tool = GmailFetchTool(source=_StaticEmailSource([message]), repository=repo, classifier=_Classifier())

    result = tool.execute(tool.input_schema(process_messages=True))

    assert result.fetched_count == 1
    assert result.processed_count == 1
    assert result.emails[0].category == "strong_ml_research_job"
    assert repo.get_message_by_source_id("gmail-1") is not None
    assert repo.get_latest_classification(message.id) is not None


def test_notification_tool_executes_approval_without_orchestrator(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    approval = ApprovalItem(
        kind=ApprovalKind.WHATSAPP_NOTIFICATION,
        target_id="msg-1",
        payload={
            "message_id": "msg-1",
            "destination": "whatsapp:+911234567890",
            "channel": "whatsapp",
            "title": "Research role",
            "body": "Please review this opportunity.",
        },
        reason="Requires approval before notify.",
        status=ApprovalStatus.PENDING,
    )
    repo.create_approval(approval)
    tool = NotificationTool(notifier=_Notifier(), repository=repo)

    result = tool.execute(tool.input_schema(approval_id=approval.id))

    assert result.status == "executed"
    assert result.approval_id == approval.id
    attempts = repo._fetchall("SELECT * FROM notification_attempts")  # type: ignore[attr-defined]
    assert len(attempts) == 1
