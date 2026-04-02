"""Created: 2026-03-30

Purpose: Implements the registry module for the shared tools platform layer.
"""

from __future__ import annotations

from typing import Any

from src.tools.base import BaseTool
from src.tools.catalog import build_tool_catalog_from_tools, catalog_to_json, catalog_to_yaml


class ToolRegistry:
    """Stores and exposes the tool set available to an agent runtime.

    The registry is intentionally simple: it is the authoritative mapping from
    tool name to tool instance. It does not execute tools and it does not make
    planning decisions. Its job is only to answer questions such as:

    - which tools are available?
    - what is the tool instance for a given name?
    - what schema/metadata catalog should be shown to a planner or LLM?

    Keeping this separate from execution makes it easier to reuse the same tool
    catalog in CLI mode, ReAct graphs, LLM planners, and future orchestrators.
    """

    def __init__(self) -> None:
        """Initializes an empty registry keyed by tool name."""
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Registers a tool instance by its declared unique name.

        Args:
            tool: The concrete tool instance to make available.
        """
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        """Returns a registered tool by name.

        Args:
            name: The unique tool name.

        Returns:
            The registered tool instance.

        Raises:
            KeyError: If no tool exists under that name.
        """
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def list_tools(self) -> list[BaseTool]:
        """Lists all registered tools.

        Returns:
            The current tool instances in registration order.
        """
        return list(self._tools.values())

    def build_catalog(self) -> list[dict[str, Any]]:
        """Builds an LLM/tool-calling-friendly catalog from registered tools.

        Returns:
            A JSON-serializable catalog describing tool names, descriptions, and
            schemas for planner or function-calling use.
        """
        return build_tool_catalog_from_tools(self.list_tools())

    def build_catalog_json(self, *, indent: int = 2) -> str:
        """Builds the registered tool catalog as JSON text.

        Args:
            indent: Indentation level for pretty-printed JSON output.

        Returns:
            The structured tool catalog serialized as JSON.
        """
        return catalog_to_json(self.build_catalog(), indent=indent)

    def build_catalog_yaml(self) -> str:
        """Builds the registered tool catalog as YAML text.

        Returns:
            The structured tool catalog serialized as YAML.

        Raises:
            RuntimeError: If PyYAML is not installed.
        """
        return catalog_to_yaml(self.build_catalog())
