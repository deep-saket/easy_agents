"""Created: 2026-03-31

Purpose: Tests the WhatsApp interface behavior.
"""

from dataclasses import dataclass, field

from src.interfaces.whatsapp import MockWhatsAppInterface, TwilioWhatsAppInterface, WhatsAppAgentBridge


class EchoAgent:
    """Provides a tiny agent stub for WhatsApp bridge tests."""

    def run(self, user_input: str, session_id: str | None = None) -> str:
        return f"{session_id}:{user_input}"


def test_mock_whatsapp_interface_captures_outbound_messages() -> None:
    interface = MockWhatsAppInterface()
    result = interface.send_message("session-1", "Hello from agent")
    assert interface.outbound_messages == [("session-1", "Hello from agent")]
    assert result["provider"] == "mock"
    assert result["status"] == "captured"


def test_whatsapp_agent_bridge_routes_message_through_agent() -> None:
    interface = MockWhatsAppInterface()
    bridge = WhatsAppAgentBridge(interface=interface, agent=EchoAgent())

    response = bridge.handle_text(session_id="wa-1", text="hello")

    assert response == "wa-1:hello"
    assert interface.outbound_messages == [("wa-1", "wa-1:hello")]


def test_whatsapp_agent_bridge_handles_webhook_payload() -> None:
    interface = MockWhatsAppInterface()
    bridge = WhatsAppAgentBridge(interface=interface, agent=EchoAgent())

    response = bridge.handle_webhook({
        "session_id": "wa-2",
        "text": "hello from webhook",
        "sender": "wa-2",
    })

    assert response == "wa-2:hello from webhook"
    assert interface.outbound_messages == [("wa-2", "wa-2:hello from webhook")]


@dataclass
class _FakeMessagesAPI:
    created: list[dict[str, str]] = field(default_factory=list)

    def create(self, *, body: str, from_: str, to: str):
        self.created.append({"body": body, "from_": from_, "to": to})
        return type(
            "FakeMessage",
            (),
            {
                "sid": "MM123",
                "status": "queued",
                "to": to,
                "from_": from_,
                "error_code": None,
                "error_message": None,
            },
        )()


@dataclass
class _FakeTwilioClient:
    messages: _FakeMessagesAPI = field(default_factory=_FakeMessagesAPI)


def test_twilio_whatsapp_interface_uses_twilio_client() -> None:
    client = _FakeTwilioClient()
    interface = TwilioWhatsAppInterface(
        account_sid="AC123",
        auth_token="token",
        whatsapp_from="whatsapp:+14155238886",
        client=client,
    )

    result = interface.send_message("whatsapp:+919999999999", "Hello from agent")

    assert client.messages.created == [{
        "body": "Hello from agent",
        "from_": "whatsapp:+14155238886",
        "to": "whatsapp:+919999999999",
    }]
    assert result == {
        "provider": "twilio",
        "sid": "MM123",
        "status": "queued",
        "to": "whatsapp:+919999999999",
        "from": "whatsapp:+14155238886",
        "error_code": None,
        "error_message": None,
    }
