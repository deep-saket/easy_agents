"""Created: 2026-03-31

Purpose: Implements the base module for the shared planner platform layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BasePlanner(ABC):
    """Defines the shared planning interface used by agents.

    A planner is responsible for deciding the next step in an agent loop. It
    does not execute tools itself and it does not own storage. Its role is to
    reason over:

    - the latest user input
    - working memory / session state
    - available tools
    - optional prior observation from a just-completed tool call

    In practical terms, the planner answers questions like:

    - should the agent respond directly?
    - should it call a tool?
    - which tool should it call next?
    - does it need clarification or routing?
    """

    @abstractmethod
    def plan(
        self,
        *,
        user_input: str,
        memory: Any | None = None,
        observation: dict[str, Any] | None = None,
        memory_context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        available_tools: list[Any] | None = None,
    ):
        """Produces the next decision for an agent turn.

        Args:
            user_input: The current user message or query.
            memory: Optional working memory or conversation state available to the
                planner for this turn.
            observation: Optional result from a previously executed tool in the
                same turn or graph loop.
            memory_context: Optional retrieved long-term memory context.
            system_prompt: Optional planner-level system prompt provided by the
                graph builder or node configuration.
            user_prompt: Optional planner-level rendered user prompt provided by
                the graph builder or node configuration.
            available_tools: Optional tool metadata available to the planner.

        Returns:
            A planner-defined decision object, typically something like a tool
            call, route, or direct response instruction.
        """
        raise NotImplementedError
