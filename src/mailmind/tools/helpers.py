from __future__ import annotations

from mailmind.core.models import MessageBundle
from mailmind.schemas.emails import EmailDetail, EmailSummary


def bundle_to_summary(bundle: MessageBundle) -> EmailSummary:
    return EmailSummary(
        id=bundle.message.id,
        source_id=bundle.message.source_id,
        from_email=bundle.message.from_email,
        from_name=bundle.message.from_name,
        subject=bundle.message.subject,
        received_at=bundle.message.received_at,
        category=bundle.classification.category.value if bundle.classification else None,
        priority_score=bundle.classification.priority_score if bundle.classification else None,
        summary=bundle.classification.summary if bundle.classification else None,
    )


def bundle_to_detail(bundle: MessageBundle) -> EmailDetail:
    return EmailDetail(
        summary=bundle_to_summary(bundle),
        body_text=bundle.message.body_text,
        labels=bundle.message.labels,
    )

