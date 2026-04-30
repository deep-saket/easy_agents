"""Prompt loaders for Connections Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_connections_agent_prompts() -> dict[str, Any]:
    prompt_path = Path(__file__).with_name("agent_prompts.yml")
    return yaml.safe_load(prompt_path.read_text(encoding="utf-8")) or {}


def load_connections_tool_catalog() -> dict[str, Any]:
    catalog_path = Path(__file__).with_name("tool_catalog.yml")
    return yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}


def render_connections_tool_catalog_yaml() -> str:
    return yaml.safe_dump(load_connections_tool_catalog(), sort_keys=False, allow_unicode=False).strip()


__all__ = [
    "load_connections_agent_prompts",
    "load_connections_tool_catalog",
    "render_connections_tool_catalog_yaml",
]
