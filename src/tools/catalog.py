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


def write_tool_catalog(tools: list[Any], path: Path) -> list[dict[str, Any]]:
    catalog = build_tool_catalog_from_tools(tools)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return catalog
