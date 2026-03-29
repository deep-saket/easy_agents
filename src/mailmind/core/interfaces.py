from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from mailmind.core.models import (
    ApprovalItem,
    ClassificationResult,
    DomainEvent,
    EmailMessage,
    MessageBundle,
    NotificationAttempt,
    NotificationPayload,
    PolicyConfig,
    ReplyDraft,
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


class MessageRepository(Protocol):
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

