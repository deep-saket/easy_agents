"""Prompt loaders for Discount Planning Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_discount_planning_prompts() -> dict[str, Any]:
    return yaml.safe_load(Path(__file__).with_name("agent_prompts.yml").read_text(encoding="utf-8")) or {}


def load_discount_planning_tool_catalog() -> dict[str, Any]:
    return yaml.safe_load(Path(__file__).with_name("tool_catalog.yml").read_text(encoding="utf-8")) or {}


def render_discount_planning_tool_catalog_yaml() -> str:
    return yaml.safe_dump(load_discount_planning_tool_catalog(), sort_keys=False, allow_unicode=False).strip()


__all__ = [
    "load_discount_planning_prompts",
    "load_discount_planning_tool_catalog",
    "render_discount_planning_tool_catalog_yaml",
]
