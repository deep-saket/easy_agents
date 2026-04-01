"""Created: 2026-03-31

Purpose: Implements the email classifier module for the mailmind agent.
"""

from __future__ import annotations

from src.tools.base import BaseTool
from src.tools.gmail.email_classifier import EmailClassifierTool as SharedEmailClassifierTool


class MailMindEmailClassifierTool(SharedEmailClassifierTool):
    """MailMind-specific wrapper over the shared classifier tool."""


__all__ = ["BaseTool", "MailMindEmailClassifierTool"]
