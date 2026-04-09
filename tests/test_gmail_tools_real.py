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
    ReplyDraft,
    SentEmail,
    SuggestedAction,
)
from src.storage.duckdb_store import DuckDBMessageRepository
from src.tools.gmail.draft_reply import DraftReplyTool
from src.tools.gmail.email_classifier import EmailClassifierTool
from src.tools.gmail.email_send import EmailSendTool
from src.tools.gmail.email_summary import EmailSummaryTool
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


class _EmailSender:
    def send(self, *, message: EmailMessage, draft: ReplyDraft, recipients=None, subject=None, body_text=None) -> SentEmail:
        resolved_recipients = recipients or [message.from_email]
        return SentEmail(
            message_id=message.id,
            draft_id=draft.id,
            provider_message_id="gmail-sent-1",
            thread_id=message.thread_id,
            recipients=resolved_recipients,
            subject=subject or draft.subject,
            status="sent",
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


def test_email_classifier_tool_defaults_to_unclassified_messages(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    message = EmailMessage(
        source_id="gmail-2",
        from_email="talent@deepmind.com",
        subject="Applied research role",
        body_text="We are hiring.",
        received_at=datetime.now(timezone.utc),
    )
    repo.save_message(message)
    tool = EmailClassifierTool(repository=repo, classifier=_Classifier())

    result = tool.execute(tool.input_schema())

    assert result.classified_count == 1
    assert result.emails[0].category == "strong_ml_research_job"


def test_email_summary_tool_defaults_to_recent_messages(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    message = EmailMessage(
        source_id="gmail-3",
        from_email="talent@deepmind.com",
        subject="Research role",
        body_text="We are hiring.",
        received_at=datetime.now(timezone.utc),
    )
    repo.save_message(message)
    repo.save_classification(_Classifier().classify(message))
    tool = EmailSummaryTool(repository=repo)

    result = tool.execute(tool.input_schema(max_items=5))

    assert result.total == 1
    assert "High-value research opportunity." in result.combined_summary


def test_draft_reply_tool_uses_builtin_generator(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    message = EmailMessage(
        source_id="gmail-4",
        from_email="talent@deepmind.com",
        from_name="Recruiter",
        subject="Research role",
        body_text="We are hiring.",
        received_at=datetime.now(timezone.utc),
    )
    repo.save_message(message)
    repo.save_classification(_Classifier().classify(message))
    tool = DraftReplyTool(repository=repo)

    result = tool.execute(tool.input_schema(message_id=message.id))

    assert result.subject.startswith("Re:")
    assert "Context noted" in result.body_text


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


def test_email_send_tool_uses_saved_draft(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    message = EmailMessage(
        source_id="gmail-5",
        thread_id="thread-5",
        from_email="talent@deepmind.com",
        subject="Research role",
        body_text="We are hiring.",
        received_at=datetime.now(timezone.utc),
    )
    repo.save_message(message)
    draft = ReplyDraft(message_id=message.id, subject="Re: Research role", body_text="Thanks for reaching out.")
    repo.save_draft(draft)
    tool = EmailSendTool(sender=_EmailSender(), repository=repo)

    result = tool.execute(tool.input_schema(message_id=message.id))

    assert result.status == "sent"
    assert result.message_id == message.id
    assert result.draft_id == draft.id
    assert result.provider_message_id == "gmail-sent-1"
    assert result.recipients == ["talent@deepmind.com"]
