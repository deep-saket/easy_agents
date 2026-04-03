"""Created: 2026-04-03

Purpose: Defines shared WhatsApp channel abstractions and transports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel


class IncomingMessage(BaseModel):
    """Represents one inbound WhatsApp-style message."""

    session_id: str
    text: str
    sender: str


class TwilioMessageCreator(Protocol):
    """Describes the minimal Twilio message client surface used by the transport."""

    def create(self, *, body: str, from_: str, to: str) -> Any:
        """Sends one outbound WhatsApp message through Twilio."""


class TwilioClientProtocol(Protocol):
    """Describes the minimal Twilio client surface used by the transport."""

    @property
    def messages(self) -> TwilioMessageCreator:
        """Returns the Twilio message API."""


@dataclass(slots=True)
class WhatsAppInterface:
    """Defines the minimal send/receive contract for a WhatsApp channel."""

    def receive_message(self) -> IncomingMessage:
        """Receives one inbound WhatsApp message."""
        raise NotImplementedError

    def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage:
        """Parses one provider webhook payload into a normalized inbound message."""

        raise NotImplementedError

    def send_message(self, session_id: str, text: str) -> dict[str, Any]:
        """Sends one outbound WhatsApp message and returns channel metadata."""
        raise NotImplementedError


@dataclass(slots=True)
class TwilioWhatsAppInterface(WhatsAppInterface):
    """Implements the shared WhatsApp channel over Twilio.

    This keeps Twilio as a transport detail underneath the generic WhatsApp
    interface used by agents and bridges. The transport can lazily construct a
    Twilio client from credentials or accept an injected client in tests.
    """

    account_sid: str
    auth_token: str
    whatsapp_from: str
    client: TwilioClientProtocol | None = None

    def receive_message(self) -> IncomingMessage:
        """Receives one inbound WhatsApp message.

        Twilio webhook ingestion is not implemented in this transport yet.
        """

        raise NotImplementedError("Twilio webhook receive flow is not implemented in the shared interface yet.")

    def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage:
        """Parses one Twilio WhatsApp webhook payload."""

        sender = str(payload.get("From", "")).strip()
        text = str(payload.get("Body", "")).strip()
        if not sender:
            raise ValueError("Twilio inbound payload is missing `From`.")
        return IncomingMessage(
            session_id=sender,
            text=text,
            sender=sender,
        )

    def send_message(self, session_id: str, text: str) -> dict[str, Any]:
        """Sends one outbound WhatsApp message via Twilio."""

        message = self._get_client().messages.create(
            body=text,
            from_=self.whatsapp_from,
            to=session_id,
        )
        return {
            "provider": "twilio",
            "sid": getattr(message, "sid", None),
            "status": str(getattr(message, "status", "")) or None,
            "to": getattr(message, "to", session_id),
            "from": getattr(message, "from_", self.whatsapp_from),
            "error_code": getattr(message, "error_code", None),
            "error_message": getattr(message, "error_message", None),
        }

    def _get_client(self) -> TwilioClientProtocol:
        """Builds or returns the configured Twilio client."""

        if self.client is not None:
            return self.client
        try:
            from twilio.rest import Client  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "Twilio SDK is not installed. Install the `twilio` package to use TwilioWhatsAppInterface."
            ) from exc
        self.client = Client(self.account_sid, self.auth_token)
        return self.client


@dataclass(slots=True)
class MockWhatsAppInterface(WhatsAppInterface):
    """Captures outbound WhatsApp messages for tests and demos."""

    outbound_messages: list[tuple[str, str]] = field(default_factory=list)

    def receive_message(self) -> IncomingMessage:
        raise NotImplementedError("Mock interface does not poll. Inject messages directly in tests or demos.")

    def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage:
        session_id = str(payload.get("session_id") or payload.get("From", ""))
        if not session_id:
            raise ValueError("Inbound payload is missing `session_id` or `From`.")
        return IncomingMessage(
            session_id=session_id,
            text=str(payload.get("text") or payload.get("Body", "")),
            sender=str(payload.get("sender") or payload.get("From", session_id)),
        )

    def send_message(self, session_id: str, text: str) -> dict[str, Any]:
        self.outbound_messages.append((session_id, text))
        return {
            "provider": "mock",
            "sid": None,
            "status": "captured",
            "to": session_id,
            "from": None,
            "error_code": None,
            "error_message": None,
        }


@dataclass(slots=True)
class WhatsAppAgentBridge:
    """Connects a generic agent runtime to a WhatsApp interface.

    This adapter keeps channel concerns out of the agent graph. It accepts an
    inbound WhatsApp message, calls the agent with the session id and message
    text, then sends the resulting response back through the interface.
    """

    interface: WhatsAppInterface
    agent: Any

    def handle_message(self, incoming: IncomingMessage) -> str:
        """Runs one inbound WhatsApp message through the agent."""

        response = self.agent.run(incoming.text, incoming.session_id)
        self.interface.send_message(incoming.session_id, response)
        return response

    def handle_text(self, *, session_id: str, text: str, sender: str = "user") -> str:
        """Convenience wrapper for tests and notebooks."""

        return self.handle_message(IncomingMessage(session_id=session_id, text=text, sender=sender))

    def handle_webhook(self, payload: dict[str, Any]) -> str:
        """Parses and handles one provider webhook payload."""

        return self.handle_message(self.interface.parse_incoming(payload))


__all__ = [
    "IncomingMessage",
    "MockWhatsAppInterface",
    "TwilioWhatsAppInterface",
    "WhatsAppAgentBridge",
    "WhatsAppInterface",
]
