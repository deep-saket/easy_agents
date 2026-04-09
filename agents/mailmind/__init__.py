"""Created: 2026-04-05

Purpose: Exports MailMind agent-specific building blocks.
"""

from agents.mailmind.helpers import MailMindEmailClassificationPayload, MailMindEmailClassifier

__all__ = [
    "MailMindEmailClassificationPayload",
    "MailMindEmailClassifier",
]
