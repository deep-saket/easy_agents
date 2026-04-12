"""Created: 2026-04-05

Purpose: Exports MailMind prompt assets.
"""

from pathlib import Path
from typing import Any

import yaml

from agents.mailmind.prompts.email_classifier import (
    MAILMIND_EMAIL_CLASSIFIER_SYSTEM_PROMPT,
    MAILMIND_EMAIL_CLASSIFIER_USER_PROMPT,
)


def load_mailmind_agent_prompts() -> dict[str, Any]:
    """Loads the YAML-backed MailMind agent prompt bundle."""
    prompt_path = Path(__file__).with_name("agent_prompts.yml")
    return yaml.safe_load(prompt_path.read_text(encoding="utf-8")) or {}


def load_mailmind_tool_catalog() -> dict[str, Any]:
    """Loads the YAML-backed MailMind React tool catalog."""
    catalog_path = Path(__file__).with_name("tool_catalog.yml")
    return yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}


def render_mailmind_tool_catalog_yaml() -> str:
    """Renders the MailMind tool catalog back to YAML text for prompt injection."""
    return yaml.safe_dump(load_mailmind_tool_catalog(), sort_keys=False, allow_unicode=False).strip()


__all__ = [
    "MAILMIND_EMAIL_CLASSIFIER_SYSTEM_PROMPT",
    "MAILMIND_EMAIL_CLASSIFIER_USER_PROMPT",
    "load_mailmind_agent_prompts",
    "load_mailmind_tool_catalog",
    "render_mailmind_tool_catalog_yaml",
]
