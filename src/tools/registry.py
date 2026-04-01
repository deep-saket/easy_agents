"""Created: 2026-03-30

Purpose: Implements the registry module for the shared tools platform layer.
"""

from __future__ import annotations

from typing import Any

from src.tools.base import BaseTool
from src.tools.catalog import build_tool_catalog_from_tools


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def build_catalog(self) -> list[dict[str, Any]]:
        return build_tool_catalog_from_tools(self.list_tools())
