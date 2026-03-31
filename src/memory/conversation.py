from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from schemas.messages import ConversationMessage


class ConversationRepository(Protocol):
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
    session_id: str
    repository: ConversationRepository
    history: list[ConversationMessage] = field(default_factory=list)
    state: dict[str, object] = field(default_factory=dict)

    @classmethod
    def load(cls, session_id: str, repository: ConversationRepository) -> "ConversationMemory":
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


__all__ = ["ConversationMemory"]
