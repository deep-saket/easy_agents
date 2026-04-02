"""Created: 2026-03-30

Purpose: Implements the orchestrator module for the shared mailmind platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.policies import MemoryPolicy
from src.memory.store import MemoryStore
from src.mailmind.core.interfaces import (
    ApprovalQueue,
    AuditLogStore,
    DraftGenerator,
    MessageClassifier,
    MessageRepository,
    Notifier,
)
from src.mailmind.core.models import (
    ApprovalItem,
    ApprovalKind,
    ClassificationResult,
    DomainEvent,
    EmailMessage,
    MessageBundle,
    NotificationPayload,
    ProcessStatus,
    SuggestedAction,
)


@dataclass(slots=True)
class MailOrchestrator:
    """Represents the mail orchestrator component."""
    repository: MessageRepository
    classifier: MessageClassifier
    drafter: DraftGenerator
    notifier: Notifier
    approval_queue: ApprovalQueue
    audit_log: AuditLogStore
    notification_destination: str
    memory_store: MemoryStore | None = None
    memory_policy: MemoryPolicy | None = None

    def process_messages(self, messages: list[EmailMessage]) -> list[MessageBundle]:
        bundles: list[MessageBundle] = []
        for message in messages:
            if self.repository.has_message(message.source_id):
                continue
            bundles.append(self.process_message(message))
        return bundles

    def process_message(self, message: EmailMessage) -> MessageBundle:
        stored = self.repository.save_message(message)
        self.audit_log.append(
            DomainEvent(event_type="message_saved", entity_id=stored.id, payload={"source_id": stored.source_id})
        )
        classification = self.classifier.classify(stored)
        self.repository.save_classification(classification)
        self.audit_log.append(
            DomainEvent(
                event_type="message_classified",
                entity_id=stored.id,
                payload=classification.model_dump(mode="json"),
            )
        )
        self._write_memory(
            {
                "event_type": "classification",
                "agent": "mailmind",
                "content": classification.model_dump(mode="json"),
                "metadata": {
                    "agent": "mailmind",
                    "message_id": stored.id,
                    "category": classification.category.value,
                    "tags": [classification.category.value, "classification"],
                    "source": "system",
                    "priority": "medium",
                },
            }
        )

        draft = None
        if classification.suggested_action in {SuggestedAction.NOTIFY_AND_DRAFT, SuggestedAction.DRAFT_ONLY}:
            draft = self.drafter.generate(stored, classification)
            self.repository.save_draft(draft)
            self.audit_log.append(
                DomainEvent(event_type="draft_created", entity_id=draft.id, payload=draft.model_dump(mode="json"))
            )

        if classification.suggested_action == SuggestedAction.NOTIFY_AND_DRAFT:
            approval = ApprovalItem(
                kind=ApprovalKind.WHATSAPP_NOTIFICATION,
                target_id=stored.id,
                payload=self._build_notification_payload(stored, classification).model_dump(mode="json"),
                reason="High-priority message requires explicit approval before outbound notification.",
            )
            self.approval_queue.enqueue(approval)
            self.audit_log.append(
                DomainEvent(
                    event_type="approval_enqueued",
                    entity_id=approval.id,
                    payload={"message_id": stored.id, "kind": approval.kind},
                )
            )

        if classification.suggested_action == SuggestedAction.ARCHIVE:
            stored.process_status = ProcessStatus.DEPRIORITIZED
            self.repository.save_message(stored)
        elif classification.suggested_action == SuggestedAction.MANUAL_REVIEW:
            stored.process_status = ProcessStatus.MANUAL_REVIEW
            self.repository.save_message(stored)
        else:
            stored.process_status = ProcessStatus.PROCESSED
            self.repository.save_message(stored)

        return MessageBundle(message=stored, classification=classification, draft=draft)

    def reprocess(self, message_id: str) -> MessageBundle:
        message = self.repository.get_message(message_id)
        if message is None:
            raise ValueError(f"Unknown message id: {message_id}")
        return self.process_message(message)

    def execute_approval(self, approval_id: str) -> ApprovalItem:
        approval = self.approval_queue.get(approval_id)
        if approval is None:
            raise ValueError(f"Unknown approval id: {approval_id}")
        payload = NotificationPayload.model_validate(approval.payload)
        attempt = self.notifier.send(payload)
        self.repository.save_notification_attempt(attempt)
        if attempt.error:
            updated = self.approval_queue.mark_failed(approval_id, attempt.error)
            self.audit_log.append(
                DomainEvent(
                    event_type="notification_failed",
                    entity_id=attempt.id,
                    payload={"message_id": attempt.message_id, "error": attempt.error},
                )
            )
            return updated
        updated = self.approval_queue.mark_executed(approval_id)
        self.audit_log.append(
            DomainEvent(
                event_type="notification_sent",
                entity_id=attempt.id,
                payload={"message_id": attempt.message_id, "destination": attempt.destination},
            )
        )
        return updated

    def reject_approval(self, approval_id: str, reason: str) -> ApprovalItem:
        updated = self.approval_queue.mark_rejected(approval_id, reason)
        self.audit_log.append(
            DomainEvent(
                event_type="approval_rejected",
                entity_id=approval_id,
                payload={"reason": reason},
            )
        )
        return updated

    def _build_notification_payload(
        self, message: EmailMessage, classification: ClassificationResult
    ) -> NotificationPayload:
        summary = classification.summary[:180]
        return NotificationPayload(
            message_id=message.id,
            destination=self.notification_destination,
            title=f"{classification.category.value}: {message.subject}",
            body=(
                f"From: {message.from_email}\n"
                f"Score: {classification.priority_score:.2f}\n"
                f"Why: {', '.join(classification.reason_codes[:3])}\n"
                f"Summary: {summary}"
            ),
        )

    def _write_memory(self, event: dict) -> None:
        if self.memory_store is None or self.memory_policy is None:
            return
        if not self.memory_policy.should_store(event):
            return
        self.memory_store.add(self.memory_policy.build_item(event))
