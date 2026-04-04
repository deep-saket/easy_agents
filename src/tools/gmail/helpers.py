"""Created: 2026-03-30

Purpose: Implements the helpers module for the shared tools platform layer.
"""

from __future__ import annotations

from src.schemas.domain import ClassificationResult, EmailMessage, MessageBundle
from src.schemas.emails import EmailDetail, EmailSummary


def message_to_summary(message: EmailMessage, classification: ClassificationResult | None = None) -> EmailSummary:
    """Builds an email summary from a stored message and optional classification."""

    return EmailSummary(
        id=message.id,
        source_id=message.source_id,
        from_email=message.from_email,
        from_name=message.from_name,
        subject=message.subject,
        received_at=message.received_at,
        category=classification.category.value if classification else None,
        priority_score=classification.priority_score if classification else None,
        summary=classification.summary if classification else None,
    )


def bundle_to_summary(bundle: MessageBundle) -> EmailSummary:
    return message_to_summary(bundle.message, bundle.classification)


def bundle_to_detail(bundle: MessageBundle) -> EmailDetail:
    return EmailDetail(
        summary=bundle_to_summary(bundle),
        body_text=bundle.message.body_text,
        labels=bundle.message.labels,
    )
