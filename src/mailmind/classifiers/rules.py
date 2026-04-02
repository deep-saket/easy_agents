"""Created: 2026-03-30

Purpose: Implements the rules module for the shared mailmind platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.mailmind.core.interfaces import MessageClassifier, PolicyProvider
from src.mailmind.core.models import Category, ClassificationResult, EmailMessage, SuggestedAction


@dataclass(slots=True)
class RulesBasedClassifier(MessageClassifier):
    """Represents the rules based classifier component."""
    policy_provider: PolicyProvider

    def classify(self, message: EmailMessage) -> ClassificationResult:
        policy = self.policy_provider.load()
        text = " ".join(
            part for part in [message.subject, message.body_text, message.from_email, message.from_name or ""] if part
        ).lower()
        score = 0.1
        reasons: list[str] = []

        if any(domain in message.from_email.lower() for domain in policy.high_priority_senders):
            score += 0.25
            reasons.append("trusted_sender_domain")

        matched_category = Category.OTHER
        best_category_score = 0.0
        for category_name, keywords in policy.positive_keywords.items():
            hits = sum(1 for keyword in keywords if keyword.lower() in text)
            if hits <= 0:
                continue
            category_score = min(0.22 * hits, 0.55)
            if category_score > best_category_score:
                best_category_score = category_score
                matched_category = self._map_category(category_name)
            score += category_score
            reasons.append(f"{category_name}_keywords:{hits}")

        negative_hits = sum(1 for keyword in policy.negative_keywords if keyword.lower() in text)
        if negative_hits:
            score -= min(0.20 * negative_hits, 0.45)
            reasons.append(f"negative_markers:{negative_hits}")

        weak_hits = sum(1 for keyword in policy.weak_recruiter_keywords if keyword.lower() in text)
        if weak_hits:
            score -= min(0.18 * weak_hits, 0.36)
            reasons.append(f"weak_recruiter_markers:{weak_hits}")
            if matched_category == Category.OTHER:
                matched_category = Category.WEAK_RECRUITER

        if "unsubscribe" in text and matched_category == Category.OTHER:
            matched_category = Category.NEWSLETTER
        elif negative_hits and matched_category == Category.OTHER:
            matched_category = Category.PROMOTION

        score = max(0.0, min(score, 1.0))
        if matched_category == Category.OTHER and score >= 0.65:
            matched_category = Category.TIME_SENSITIVE_PROFESSIONAL if "deadline" in text or "today" in text else Category.OTHER

        action = self._choose_action(score, policy)
        confidence = min(0.55 + abs(score - 0.5), 0.99)
        summary = self._build_summary(message, matched_category, score, reasons)
        return ClassificationResult(
            message_id=message.id,
            priority_score=score,
            category=matched_category,
            confidence=confidence,
            reason_codes=reasons or ["default_low_signal"],
            suggested_action=action,
            summary=summary,
        )

    @staticmethod
    def _map_category(category_name: str) -> Category:
        mapping = {
            "strong_ml_research_job": Category.STRONG_ML_RESEARCH_JOB,
            "deep_tech_opportunity": Category.DEEP_TECH_OPPORTUNITY,
            "network_event": Category.NETWORK_EVENT,
            "time_sensitive": Category.TIME_SENSITIVE_PROFESSIONAL,
            "alumni_reconnect": Category.ALUMNI_RECONNECT,
            "personal_exceptional": Category.PERSONAL_EXCEPTIONAL,
        }
        return mapping.get(category_name, Category.OTHER)

    @staticmethod
    def _choose_action(score: float, policy) -> SuggestedAction:
        if score >= policy.high_priority_threshold:
            return SuggestedAction.NOTIFY_AND_DRAFT
        if score >= policy.draft_generation_threshold:
            return SuggestedAction.DRAFT_ONLY
        if policy.manual_review_band["min"] <= score <= policy.manual_review_band["max"]:
            return SuggestedAction.MANUAL_REVIEW
        return SuggestedAction.ARCHIVE

    @staticmethod
    def _build_summary(message: EmailMessage, category: Category, score: float, reasons: list[str]) -> str:
        return (
            f"{category.value} scored {score:.2f} for '{message.subject}' "
            f"from {message.from_email} because {', '.join(reasons[:3]) or 'signal was weak'}."
        )

