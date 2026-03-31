"""Created: 2026-03-31

Purpose: Implements the router module for the shared planner platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Router:
    """Future multi-agent router placeholder."""

    def route(self, user_input: str) -> str:
        del user_input
        return "mailmind"

