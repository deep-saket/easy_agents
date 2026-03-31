"""Created: 2026-03-30

Purpose: Implements the simple module for the shared mailmind platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from mailmind.core.interfaces import DraftGenerator
from mailmind.core.models import Category, ClassificationResult, EmailMessage, ReplyDraft


@dataclass(slots=True)
class SimpleReplyDrafter(DraftGenerator):
    def generate(self, message: EmailMessage, classification: ClassificationResult) -> ReplyDraft:
        opener = self._opener_for(classification.category)
        body = (
            f"{opener}\n\n"
            f"Thank you for reaching out about \"{message.subject}\". "
            "This looks relevant, and I would be glad to continue the conversation.\n\n"
            "Please share a couple of time options or any additional context that would help me prepare.\n\n"
            "Best,\n"
            "Saket"
        )
        return ReplyDraft(
            message_id=message.id,
            subject=f"Re: {message.subject}",
            body_text=body,
        )

    @staticmethod
    def _opener_for(category: Category) -> str:
        mapping = {
            Category.STRONG_ML_RESEARCH_JOB: "This opportunity aligns strongly with my current research and engineering focus.",
            Category.DEEP_TECH_OPPORTUNITY: "The company-building angle here is especially interesting to me.",
            Category.NETWORK_EVENT: "This invitation looks valuable and well-curated.",
            Category.ALUMNI_RECONNECT: "It would be good to reconnect on this.",
            Category.PERSONAL_EXCEPTIONAL: "Thank you for writing. I appreciate the note.",
        }
        return mapping.get(category, "Thank you for the note.")

