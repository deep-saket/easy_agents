"""Created: 2026-04-04

Purpose: Defines shared domain records and enums for framework-level email and
tool workflows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Returns the current UTC timestamp."""
    return datetime.now(timezone.utc)


class Category(str, Enum):
    """Represents the normalized email category."""

    STRONG_ML_RESEARCH_JOB = "strong_ml_research_job"
    DEEP_TECH_OPPORTUNITY = "deep_tech_opportunity"
    NETWORK_EVENT = "network_event"
    TIME_SENSITIVE_PROFESSIONAL = "time_sensitive_professional"
    ALUMNI_RECONNECT = "alumni_reconnect"
    PERSONAL_EXCEPTIONAL = "personal_exceptional"
    PROMOTION = "promotion"
    NEWSLETTER = "newsletter"
    WEAK_RECRUITER = "weak_recruiter"
    OTHER = "other"


class SuggestedAction(str, Enum):
    """Represents the suggested post-classification action."""

    NOTIFY_AND_DRAFT = "notify_and_draft"
    DRAFT_ONLY = "draft_only"
    MANUAL_REVIEW = "manual_review"
    ARCHIVE = "archive"
    IGNORE = "ignore"


class ActionType(str, Enum):
    """Represents the type of user action implied by a message."""

    REPLY = "reply"
    SCHEDULE = "schedule"
    REVIEW = "review"
    NONE = "none"


class ApprovalKind(str, Enum):
    """Represents the type of approval request."""

    WHATSAPP_NOTIFICATION = "whatsapp_notification"


class ApprovalStatus(str, Enum):
    """Represents the status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


class NotificationStatus(str, Enum):
    """Represents the status of a notification attempt."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class ProcessStatus(str, Enum):
    """Represents the processing state of a stored message."""

    NEW = "new"
    PROCESSED = "processed"
    DEPRIORITIZED = "deprioritized"
    MANUAL_REVIEW = "manual_review"


class EmailMessage(BaseModel):
    """Represents one stored email message."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str
    thread_id: str | None = None
    from_name: str | None = None
    from_email: str
    to: list[str] = Field(default_factory=list)
    subject: str
    body_text: str
    body_html: str | None = None
    received_at: datetime
    labels: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    process_status: ProcessStatus = ProcessStatus.NEW
    created_at: datetime = Field(default_factory=utc_now)


class ClassificationResult(BaseModel):
    """Represents the latest classification for an email message."""

    message_id: str
    priority_score: float
    impact_score: float = 0.0
    category: Category
    requires_action: bool = False
    action_type: ActionType = ActionType.NONE
    confidence: float
    reason_codes: list[str]
    reasoning: str = ""
    suggested_action: SuggestedAction
    summary: str
    created_at: datetime = Field(default_factory=utc_now)


class ReplyDraft(BaseModel):
    """Represents a generated reply draft."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    message_id: str
    subject: str
    body_text: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SentEmail(BaseModel):
    """Represents one outbound email send result."""

    message_id: str
    draft_id: str | None = None
    provider_message_id: str | None = None
    thread_id: str | None = None
    recipients: list[str] = Field(default_factory=list)
    subject: str
    status: str = "sent"
    created_at: datetime = Field(default_factory=utc_now)


class NotificationPayload(BaseModel):
    """Represents the outbound notification payload."""

    message_id: str
    destination: str
    channel: str = "whatsapp"
    title: str
    body: str


class ApprovalItem(BaseModel):
    """Represents one pending or completed approval item."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: ApprovalKind
    target_id: str
    payload: dict[str, Any]
    status: ApprovalStatus = ApprovalStatus.PENDING
    reason: str
    created_at: datetime = Field(default_factory=utc_now)
    decided_at: datetime | None = None


class NotificationAttempt(BaseModel):
    """Represents one notification delivery attempt."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    message_id: str
    channel: str
    destination: str
    payload: dict[str, Any]
    status: NotificationStatus
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class DomainEvent(BaseModel):
    """Represents one structured audit event."""

    event_type: str
    entity_id: str
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=utc_now)


class PolicyConfig(BaseModel):
    """Represents a loaded email-processing policy configuration."""

    profile: dict[str, Any]
    high_priority_senders: list[str] = Field(default_factory=list)
    positive_keywords: dict[str, list[str]] = Field(default_factory=dict)
    negative_keywords: list[str] = Field(default_factory=list)
    weak_recruiter_keywords: list[str] = Field(default_factory=list)
    category_thresholds: dict[str, float] = Field(default_factory=dict)
    manual_review_band: dict[str, float] = Field(default_factory=lambda: {"min": 0.45, "max": 0.74})
    high_priority_threshold: float = 0.75
    draft_generation_threshold: float = 0.70


class MessageBundle(BaseModel):
    """Represents a message with optional derived artifacts."""

    message: EmailMessage
    classification: ClassificationResult | None = None
    draft: ReplyDraft | None = None


class ToolExecutionLog(BaseModel):
    """Represents one structured tool execution log entry."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    tool_name: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None = None
    status: str
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "ActionType",
    "ApprovalItem",
    "ApprovalKind",
    "ApprovalStatus",
    "Category",
    "ClassificationResult",
    "DomainEvent",
    "EmailMessage",
    "MessageBundle",
    "NotificationAttempt",
    "NotificationPayload",
    "NotificationStatus",
    "PolicyConfig",
    "ProcessStatus",
    "ReplyDraft",
    "SentEmail",
    "SuggestedAction",
    "ToolExecutionLog",
    "utc_now",
]
