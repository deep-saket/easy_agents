from __future__ import annotations

from dataclasses import dataclass

from memory.conversation import ConversationMemory


@dataclass(slots=True)
class SessionStore:
    repository: object

    def load(self, session_id: str) -> ConversationMemory:
        return ConversationMemory.load(session_id, self.repository)

