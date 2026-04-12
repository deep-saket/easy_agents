"""Created: 2026-04-05

Purpose: Implements the MailMind-specific LLM email classifier.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from agents.mailmind.prompts.email_classifier import (
    MAILMIND_EMAIL_CLASSIFIER_SYSTEM_PROMPT,
    MAILMIND_EMAIL_CLASSIFIER_USER_PROMPT,
)
from src.helpers import LLMClassifierTemplate
from src.interfaces.email import MessageClassifier
from src.schemas.domain import (
    ActionType,
    Category,
    ClassificationResult,
    EmailMessage,
    SuggestedAction,
)


class MailMindEmailClassificationPayload(BaseModel):
    """Represents the structured LLM payload for MailMind email classification."""

    category: Category
    requires_action: bool
    action_type: ActionType
    impact_score: float = Field(ge=0.0, le=1.0)
    priority_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    reason_codes: list[str] = Field(default_factory=list)
    suggested_action: SuggestedAction
    summary: str


@dataclass(slots=True)
class MailMindEmailClassifier(LLMClassifierTemplate[MailMindEmailClassificationPayload], MessageClassifier):
    """Classifies email messages using MailMind-specific prompts and classes."""

    def __init__(
        self,
        llm: object,
        *,
        system_prompt: str = MAILMIND_EMAIL_CLASSIFIER_SYSTEM_PROMPT,
        user_prompt: str = MAILMIND_EMAIL_CLASSIFIER_USER_PROMPT,
        class_details_path: Path | None = None,
    ) -> None:
        class_details = self._load_class_details(class_details_path)
        LLMClassifierTemplate.__init__(
            self,
            llm=llm,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            classification_classes=list(class_details.keys()),
            class_details=class_details,
            output_schema=MailMindEmailClassificationPayload,
        )

    def classify(self, message: EmailMessage) -> ClassificationResult:
        payload = LLMClassifierTemplate.classify(self, self._build_payload(message))
        return ClassificationResult(
            message_id=message.id,
            priority_score=payload.priority_score,
            impact_score=payload.impact_score,
            category=payload.category,
            requires_action=payload.requires_action,
            action_type=payload.action_type,
            confidence=payload.confidence,
            reason_codes=payload.reason_codes,
            reasoning=payload.reason,
            suggested_action=payload.suggested_action,
            summary=payload.summary,
        )

    @staticmethod
    def _build_payload(message: EmailMessage) -> dict[str, object]:
        return {
            "id": message.id,
            "source_id": message.source_id,
            "thread_id": message.thread_id,
            "from_name": message.from_name,
            "from_email": message.from_email,
            "to": message.to,
            "subject": message.subject,
            "body_text": message.body_text,
            "body_html": message.body_html,
            "received_at": message.received_at.isoformat(),
            "labels": message.labels,
        }

    @staticmethod
    def _load_class_details(class_details_path: Path | None) -> dict[str, object]:
        path = class_details_path or (Path(__file__).resolve().parent.parent / "prompts" / "email_classifier_classes.json")
        return json.loads(path.read_text(encoding="utf-8"))
