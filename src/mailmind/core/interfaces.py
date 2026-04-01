"""Created: 2026-03-30

Purpose: Implements the interfaces module for the shared mailmind platform layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Protocol

from src.memory.conversation import ConversationRepository
from src.mailmind.core.models import (
    ApprovalItem,
    ClassificationResult,
    DomainEvent,
    EmailMessage,
    MessageBundle,
    NotificationAttempt,
    NotificationPayload,
    PolicyConfig,
    ReplyDraft,
    ToolExecutionLog,
    ConversationMessage,
)


class EmailSource(Protocol):
    def fetch_new_messages(self) -> list[EmailMessage]:
        ...


class MessageClassifier(Protocol):
    def classify(self, message: EmailMessage) -> ClassificationResult:
        ...


class DraftGenerator(Protocol):
    def generate(self, message: EmailMessage, classification: ClassificationResult) -> ReplyDraft:
        ...


class Notifier(Protocol):
    def send(self, payload: NotificationPayload) -> NotificationAttempt:
        ...


class ApprovalQueue(Protocol):
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
    """Defines the full MailMind persistence contract.

    `MessageRepository` is the larger MailMind-specific repository interface.
    It extends the shared `ConversationRepository` protocol so that one storage
    implementation can back both:

    - working memory for active conversations
    - MailMind domain storage for emails, classifications, drafts, approvals,
      notifications, and tool logs

    This explicit inheritance exists to avoid the appearance of two separate
    conversation repository abstractions. The conversation-related methods live
    in the shared base protocol, while MailMind adds its domain-specific
    persistence operations here.
    """

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
    def append(self, event: DomainEvent) -> None:
        ...

    def read_recent(self, limit: int = 200) -> list[dict[str, object]]:
        ...


class PolicyProvider(Protocol):
    def load(self) -> PolicyConfig:
        ...


class SupportsReprocess(ABC):
    @abstractmethod
    def reprocess(self, message_id: str) -> MessageBundle:
        raise NotImplementedError
