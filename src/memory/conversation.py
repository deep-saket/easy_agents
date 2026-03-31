"""Created: 2026-03-31

Purpose: Implements the conversation module for the shared memory platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from schemas.messages import ConversationMessage


class ConversationRepository(Protocol):
    """Defines the persistence contract for session-scoped working memory.

    `ConversationRepository` is intentionally separate from the long-term
    memory store abstraction. It is not used for semantic, episodic, error, or
    reflection memory. Instead, it persists the short-lived state that an agent
    needs while a conversation is active, such as:

    - recent message history
    - pending clarification flags
    - the last query type
    - temporary per-session planner state

    Any repository that implements these methods can back `ConversationMemory`,
    whether the implementation uses SQLite, Redis, files, or an in-memory test
    double.
    """

    def list_conversation_messages(self, session_id: str) -> list[ConversationMessage]:
        ...

    def get_conversation_state(self, session_id: str) -> dict[str, object] | None:
        ...

    def add_conversation_message(self, message: ConversationMessage) -> None:
        ...

    def save_conversation_state(self, session_id: str, state: dict[str, object]) -> None:
        ...


@dataclass(slots=True)
class ConversationMemory:
    """Represents working memory for one active conversation session.

    This class is the runtime object the agent actually interacts with during a
    conversation. It holds two kinds of short-lived state:

    - `history`: recent user/agent messages for the current session
    - `state`: structured control state for the planner, such as pending
      clarifications or the last search filters

    This is intentionally different from the long-term memory system:

    - `ConversationMemory` is session-scoped and mutable.
    - long-term memory stores reusable knowledge and past events across runs.

    In other words, if the agent needs to remember something *just for the
    current chat*, it belongs here. If it needs to remember something across
    sessions or agents, it belongs in semantic or episodic memory instead.
    """

    session_id: str
    repository: ConversationRepository
    history: list[ConversationMessage] = field(default_factory=list)
    state: dict[str, object] = field(default_factory=dict)

    @classmethod
    def load(cls, session_id: str, repository: ConversationRepository) -> "ConversationMemory":
        """Loads working memory for a session from persistent storage.

        Args:
            session_id: The session identifier for the active conversation.
            repository: Storage backend that persists session messages and
                session state.

        Returns:
            A populated `ConversationMemory` instance for the session.
        """
        return cls(
            session_id=session_id,
            repository=repository,
            history=repository.list_conversation_messages(session_id),
            state=repository.get_conversation_state(session_id) or {},
        )

    def add_user_message(self, content: str) -> None:
        """Appends a user message to the session history and persists it.

        Args:
            content: Raw user message text to record.
        """
        message = ConversationMessage(session_id=self.session_id, role="user", content=content)
        self.repository.add_conversation_message(message)
        self.history.append(message)

    def add_agent_message(self, content: str) -> None:
        """Appends an agent message to the session history and persists it.

        Args:
            content: Agent response text to record.
        """
        message = ConversationMessage(session_id=self.session_id, role="agent", content=content)
        self.repository.add_conversation_message(message)
        self.history.append(message)

    def set_state(self, **kwargs: object) -> None:
        """Updates structured per-session working-memory state.

        Args:
            **kwargs: Key-value pairs to merge into the existing session state.
        """
        self.state.update(kwargs)
        self.repository.save_conversation_state(self.session_id, self.state)

    def clear_pending(self) -> None:
        """Clears the planner's pending clarification state for the session.

        This is used after the user resolves a follow-up question so the agent
        does not keep treating later turns as clarification responses.
        """
        self.state.pop("pending_choice", None)
        self.state.pop("last_query_type", None)
        self.state.pop("last_search_filters", None)
        self.repository.save_conversation_state(self.session_id, self.state)


__all__ = ["ConversationMemory"]
