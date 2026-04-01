"""Created: 2026-03-30

Purpose: Implements the queue module for the shared mailmind platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.mailmind.core.interfaces import ApprovalQueue, MessageRepository
from src.mailmind.core.models import ApprovalItem, ApprovalStatus


@dataclass(slots=True)
class LocalApprovalQueue(ApprovalQueue):
    repository: MessageRepository

    def enqueue(self, item: ApprovalItem) -> ApprovalItem:
        return self.repository.create_approval(item)

    def get(self, approval_id: str) -> ApprovalItem | None:
        return self.repository.get_approval(approval_id)

    def list_pending(self) -> list[ApprovalItem]:
        return self.repository.list_approvals(pending_only=True)

    def mark_rejected(self, approval_id: str, reason: str) -> ApprovalItem:
        item = self._require(approval_id)
        item.status = ApprovalStatus.REJECTED
        item.reason = reason
        item.decided_at = datetime.now(timezone.utc)
        return self.repository.update_approval(item)

    def mark_executed(self, approval_id: str) -> ApprovalItem:
        item = self._require(approval_id)
        item.status = ApprovalStatus.EXECUTED
        item.decided_at = datetime.now(timezone.utc)
        return self.repository.update_approval(item)

    def mark_failed(self, approval_id: str, reason: str) -> ApprovalItem:
        item = self._require(approval_id)
        item.status = ApprovalStatus.FAILED
        item.reason = reason
        item.decided_at = datetime.now(timezone.utc)
        return self.repository.update_approval(item)

    def _require(self, approval_id: str) -> ApprovalItem:
        item = self.repository.get_approval(approval_id)
        if item is None:
            raise ValueError(f"Unknown approval id: {approval_id}")
        return item

