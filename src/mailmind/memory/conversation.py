"""Created: 2026-03-31

Purpose: Implements the conversation module for the shared mailmind platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mailmind.core.interfaces import MessageRepository
from mailmind.core.models import ConversationMessage


@dataclass(slots=True)
class ConversationMemory:
    session_id: str
    repository: MessageRepository
    history: list[ConversationMessage] = field(default_factory=list)
    state: dict[str, object] = field(default_factory=dict)

    @classmethod
    def load(cls, session_id: str, repository: MessageRepository) -> "ConversationMemory":
        return cls(
            session_id=session_id,
            repository=repository,
            history=repository.list_conversation_messages(session_id),
            state=repository.get_conversation_state(session_id) or {},
        )

    def add_user_message(self, content: str) -> None:
        message = ConversationMessage(session_id=self.session_id, role="user", content=content)
        self.repository.add_conversation_message(message)
        self.history.append(message)

    def add_agent_message(self, content: str) -> None:
        message = ConversationMessage(session_id=self.session_id, role="agent", content=content)
        self.repository.add_conversation_message(message)
        self.history.append(message)

    def set_state(self, **kwargs: object) -> None:
        self.state.update(kwargs)
        self.repository.save_conversation_state(self.session_id, self.state)

    def clear_pending(self) -> None:
        self.state.pop("pending_choice", None)
        self.state.pop("last_query_type", None)
        self.state.pop("last_search_filters", None)
        self.repository.save_conversation_state(self.session_id, self.state)

