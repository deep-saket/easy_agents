"""Created: 2026-03-31

Purpose: Implements the session store module for the shared memory platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.conversation import ConversationMemory


@dataclass(slots=True)
class SessionStore:
    """Provides a thin adapter from repository storage to `ConversationMemory`.

    The shared ReAct agent depends on a simple session-store abstraction so it
    does not need to know which repository implementation backs working memory.
    `SessionStore` is that adapter for the current repository-based setup.
    """

    repository: object

    def load(self, session_id: str) -> ConversationMemory:
        """Loads the working-memory object for a session identifier.

        Args:
            session_id: Identifier of the conversation session being resumed or
                created.

        Returns:
            The `ConversationMemory` instance for that session.
        """
        return ConversationMemory.load(session_id, self.repository)
