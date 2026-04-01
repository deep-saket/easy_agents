"""Created: 2026-03-31

Purpose: Defines shared protocol and state types for agent graph nodes.
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class PlannerProtocol(Protocol):
    """Describes the planner interface consumed by shared graph nodes."""

    def plan(
        self,
        *,
        user_input: str,
        memory: Any,
        observation: dict[str, Any] | None = None,
        memory_context: dict[str, Any] | None = None,
    ) -> Any:
        """Plans the next agent step for the current turn."""
        ...


class MemoryProtocol(Protocol):
    """Describes the working-memory contract needed by shared graph nodes."""

    def add_user_message(self, content: str) -> None:
        """Persists one user message in session working memory."""
        ...

    def add_agent_message(self, content: str) -> None:
        """Persists one agent message in session working memory."""
        ...

    def set_state(self, **kwargs: object) -> None:
        """Stores session-scoped state updates for later turns."""
        ...


class SessionStoreProtocol(Protocol):
    """Describes the session store used to load working memory by session id."""

    def load(self, session_id: str) -> MemoryProtocol:
        """Loads or creates the conversation working memory for a session."""
        ...


class ReActState(TypedDict, total=False):
    """Represents the shared graph state passed between agent nodes."""

    user_input: str
    memory: MemoryProtocol
    memory_context: dict[str, Any]
    decision: Any
    observation: dict[str, Any] | None
    response: str
    steps: int
    route: str
    approval_item: Any
    approval_result: Any
