"""Created: 2026-03-31

Purpose: Implements the config module for the mailmind agent.
"""

from __future__ import annotations

from src.utils.config import AppSettings


class MailMindSettings(AppSettings):
    """MailMind-specific settings wrapper over shared platform config."""

