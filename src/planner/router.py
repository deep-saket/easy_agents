from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Router:
    """Future multi-agent router placeholder."""

    def route(self, user_input: str) -> str:
        del user_input
        return "mailmind"

