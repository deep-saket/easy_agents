"""Created: 2026-04-04

Purpose: Exposes reusable data-source adapters for the framework.
"""

from src.sources.gmail import GmailEmailSource
from src.sources.gmail_sender import GmailEmailSender

__all__ = ["GmailEmailSource", "GmailEmailSender"]
