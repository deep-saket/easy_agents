"""Created: 2026-03-31

Purpose: Defines shared protocol and state types for agent graph nodes.
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


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


class AgentState(TypedDict, total=False):
    """Represents the neutral shared state passed between graph nodes.

    The state is intentionally generic so the platform can compose different
    agent graphs from the same node vocabulary. Although some current nodes are
    inspired by a ReAct-style loop, the state itself should not be named after
    a single reasoning pattern.
    """

    user_input: str
    memory: MemoryProtocol | None
    memory_context: dict[str, Any]
    intent: dict[str, Any]
    decision: Any
    memory_updates: list[dict[str, Any]]
    stored_memories: list[Any]
    observation: dict[str, Any] | None
    available_tools: list[Any] | None
    response: str
    steps: int
    route: str
    approval_item: Any
    approval_result: Any
    confidence: float


class NodeUpdate(TypedDict, total=False):
    """Represents a partial state update emitted by one graph node.

    LangGraph merges these updates into the shared state after each node
    finishes. Keeping this as a dedicated alias makes the node contract easier
    to read and document than reusing the full state type everywhere.
    """

    user_input: str
    memory: MemoryProtocol | None
    memory_context: dict[str, Any]
    intent: dict[str, Any]
    decision: Any
    memory_updates: list[dict[str, Any]]
    stored_memories: list[Any]
    observation: dict[str, Any] | None
    available_tools: list[Any] | None
    response: str
    steps: int
    route: str
    approval_item: Any
    approval_result: Any
    confidence: float


# Backward compatibility alias during the transition away from a ReAct-specific
# state name.
ReActState = AgentState
