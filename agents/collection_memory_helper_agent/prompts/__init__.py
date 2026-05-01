"""Prompt loaders for collection memory helper agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_collection_memory_helper_prompts() -> dict[str, Any]:
    path = Path(__file__).with_name("agent_prompts.yml")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_collection_memory_helper_tool_catalog() -> dict[str, Any]:
    path = Path(__file__).with_name("tool_catalog.yml")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def render_collection_memory_helper_tool_catalog_yaml() -> str:
    return yaml.safe_dump(load_collection_memory_helper_tool_catalog(), sort_keys=False, allow_unicode=False).strip()


__all__ = [
    "load_collection_memory_helper_prompts",
    "load_collection_memory_helper_tool_catalog",
    "render_collection_memory_helper_tool_catalog_yaml",
]
