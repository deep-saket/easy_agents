"""Created: 2026-04-04

Purpose: Defines shared protocols for email-centric framework components.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Protocol

from src.memory.conversation import ConversationRepository
from src.schemas.domain import (
    ApprovalItem,
    ClassificationResult,
    DomainEvent,
    EmailMessage,
    MessageBundle,
    NotificationAttempt,
    NotificationPayload,
    PolicyConfig,
    ReplyDraft,
    SentEmail,
    ToolExecutionLog,
)


class EmailSource(Protocol):
    """Describes a source that can fetch new email messages."""

    def fetch_new_messages(self) -> list[EmailMessage]:
        ...


class MessageClassifier(Protocol):
    """Describes a component that classifies a stored email message."""

    def classify(self, message: EmailMessage) -> ClassificationResult:
        ...


class DraftGenerator(Protocol):
    """Describes a component that generates reply drafts."""

    def generate(self, message: EmailMessage, classification: ClassificationResult) -> ReplyDraft:
        ...


class EmailSender(Protocol):
    """Describes a transport that can send an outbound email."""

    def send(
        self,
        *,
        message: EmailMessage,
        draft: ReplyDraft,
        recipients: list[str] | None = None,
        subject: str | None = None,
        body_text: str | None = None,
    ) -> SentEmail:
        ...


class Notifier(Protocol):
    """Describes a notification transport."""

    def send(self, payload: NotificationPayload) -> NotificationAttempt:
        ...


class ApprovalQueue(Protocol):
    """Describes approval queue operations."""

    def enqueue(self, item: ApprovalItem) -> ApprovalItem:
        ...

    def get(self, approval_id: str) -> ApprovalItem | None:
        ...

    def list_pending(self) -> list[ApprovalItem]:
        ...

    def mark_rejected(self, approval_id: str, reason: str) -> ApprovalItem:
        ...

    def mark_executed(self, approval_id: str) -> ApprovalItem:
        ...

    def mark_failed(self, approval_id: str, reason: str) -> ApprovalItem:
        ...


class MessageRepository(ConversationRepository, Protocol):
    """Defines the persistence contract for stored messages and conversations."""

    def init_db(self) -> None:
        ...

    def has_message(self, source_id: str) -> bool:
        ...

    def save_message(self, message: EmailMessage) -> EmailMessage:
        ...

    def get_message(self, message_id: str) -> EmailMessage | None:
        ...

    def get_message_by_source_id(self, source_id: str) -> EmailMessage | None:
        ...

    def list_messages(self, *, search: str | None = None, only_important: bool = False) -> list[MessageBundle]:
        ...

    def search_messages(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sender: str | None = None,
        limit: int = 100,
        only_important: bool = False,
    ) -> list[MessageBundle]:
        ...

    def save_classification(self, result: ClassificationResult) -> ClassificationResult:
        ...

    def get_latest_classification(self, message_id: str) -> ClassificationResult | None:
        ...

    def save_draft(self, draft: ReplyDraft) -> ReplyDraft:
        ...

    def get_draft(self, message_id: str) -> ReplyDraft | None:
        ...

    def list_drafts(self) -> list[ReplyDraft]:
        ...

    def create_approval(self, item: ApprovalItem) -> ApprovalItem:
        ...

    def get_approval(self, approval_id: str) -> ApprovalItem | None:
        ...

    def list_approvals(self, *, pending_only: bool = False) -> list[ApprovalItem]:
        ...

    def update_approval(self, item: ApprovalItem) -> ApprovalItem:
        ...

    def save_notification_attempt(self, attempt: NotificationAttempt) -> NotificationAttempt:
        ...

    def save_tool_log(self, log: ToolExecutionLog) -> ToolExecutionLog:
        ...

    def list_tool_logs(self, *, limit: int = 200, tool_name: str | None = None) -> list[ToolExecutionLog]:
        ...

    def set_processing_state(self, key: str, value: dict[str, str]) -> None:
        ...

    def get_processing_state(self, key: str) -> dict[str, str] | None:
        ...


class AuditLogStore(Protocol):
    """Describes a structured audit-event sink."""

    def append(self, event: DomainEvent) -> None:
        ...

    def read_recent(self, limit: int = 200) -> list[dict[str, object]]:
        ...


class PolicyProvider(Protocol):
    """Describes a source of policy configuration."""

    def load(self) -> PolicyConfig:
        ...


class SupportsReprocess(ABC):
    """Marks a component that can reprocess a message by id."""

    @abstractmethod
    def reprocess(self, message_id: str) -> MessageBundle:
        raise NotImplementedError


__all__ = [
    "ApprovalQueue",
    "AuditLogStore",
    "DraftGenerator",
    "EmailSender",
    "EmailSource",
    "MessageClassifier",
    "MessageRepository",
    "Notifier",
    "PolicyProvider",
    "SupportsReprocess",
]
