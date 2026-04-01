"""Created: 2026-03-30

Purpose: Implements the llm module for the shared mailmind platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.llm.huggingface import HuggingFaceLLM
from src.mailmind.core.interfaces import MessageClassifier
from src.mailmind.core.models import Category, ClassificationResult, EmailMessage, SuggestedAction


@dataclass(slots=True)
class OptionalLLMClassifierAdapter(MessageClassifier):
    fallback: MessageClassifier
    llm: HuggingFaceLLM | None = None
    enabled: bool = False

    def classify(self, message: EmailMessage) -> ClassificationResult:
        if not self.enabled or self.llm is None:
            return self.fallback.classify(message)
        fallback_result = self.fallback.classify(message)
        try:
            payload = self.llm.generate_json(self._system_prompt(), self._user_prompt(message, fallback_result))
            return ClassificationResult(
                message_id=message.id,
                priority_score=float(payload["priority_score"]),
                category=Category(str(payload["category"])),
                confidence=float(payload["confidence"]),
                reason_codes=[str(item) for item in payload["reason_codes"]],
                suggested_action=SuggestedAction(str(payload["suggested_action"])),
                summary=str(payload["summary"]),
            )
        except Exception as exc:
            fallback_result.reason_codes.append(f"llm_fallback:{type(exc).__name__}")
            return fallback_result

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You classify professional email priority for a machine learning researcher and engineer. "
            "Return only one JSON object with keys priority_score, category, confidence, reason_codes, "
            "suggested_action, summary. "
            "Valid category values: strong_ml_research_job, deep_tech_opportunity, network_event, "
            "time_sensitive_professional, alumni_reconnect, personal_exceptional, promotion, newsletter, "
            "weak_recruiter, other. "
            "Valid suggested_action values: notify_and_draft, draft_only, manual_review, archive, ignore."
        )

    @staticmethod
    def _user_prompt(message: EmailMessage, fallback_result: ClassificationResult) -> str:
        return (
            f"From: {message.from_email}\n"
            f"Subject: {message.subject}\n"
            f"Body:\n{message.body_text}\n\n"
            "Rules-based prior classification:\n"
            f"{fallback_result.model_dump_json(indent=2)}\n"
            "Use the prior as guidance, but improve it if the email content clearly supports a better classification."
        )
