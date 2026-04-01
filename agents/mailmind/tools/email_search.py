"""Created: 2026-03-31

Purpose: Implements the email search module for the mailmind agent.
"""

from __future__ import annotations

from src.tools.base import BaseTool
from src.tools.gmail.email_search import EmailSearchTool as SharedEmailSearchTool


class MailMindEmailSearchTool(SharedEmailSearchTool):
    """MailMind-specific wrapper over the shared email search tool."""


__all__ = ["BaseTool", "MailMindEmailSearchTool"]
