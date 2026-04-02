"""Created: 2026-03-31

Purpose: Implements the whatsapp module for the shared mailmind platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel


class IncomingMessage(BaseModel):
    """Represents the incoming message component."""
    session_id: str
    text: str
    sender: str


@dataclass(slots=True)
class WhatsAppInterface:
    """Defines the interface for whats app interactions."""
    def receive_message(self) -> IncomingMessage:
        raise NotImplementedError

    def send_message(self, session_id: str, text: str) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class MockWhatsAppInterface(WhatsAppInterface):
    """Defines the interface for mock whats app interactions."""
    outbound_messages: list[tuple[str, str]] = field(default_factory=list)

    def receive_message(self) -> IncomingMessage:
        raise NotImplementedError("Mock interface does not poll. Inject messages directly in tests/CLI.")

    def send_message(self, session_id: str, text: str) -> None:
        self.outbound_messages.append((session_id, text))
