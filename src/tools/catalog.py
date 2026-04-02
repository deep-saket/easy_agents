"""Created: 2026-03-31

Purpose: Implements the catalog module for the shared tools platform layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_tool_catalog_from_tools(tools: list[Any]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for tool in tools:
        schema = tool.input_schema.model_json_schema()
        catalog.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": schema,
                },
            }
        )
    return catalog


def catalog_to_json(catalog: list[dict[str, Any]], *, indent: int = 2) -> str:
    """Serializes a structured tool catalog into JSON text."""
    return json.dumps(catalog, indent=indent, ensure_ascii=True)


def catalog_to_yaml(catalog: list[dict[str, Any]]) -> str:
    """Serializes a structured tool catalog into YAML text.

    Falls back to JSON-compatible key ordering through PyYAML when available.
    """
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required for YAML tool catalog output.") from exc
    return yaml.safe_dump(catalog, sort_keys=False, allow_unicode=False)


def write_tool_catalog(tools: list[Any], path: Path) -> list[dict[str, Any]]:
    catalog = build_tool_catalog_from_tools(tools)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return catalog
