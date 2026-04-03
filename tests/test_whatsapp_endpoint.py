"""Created: 2026-04-03

Purpose: Tests the external WhatsApp webhook endpoint module.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from endpoints.whatsapp import create_whatsapp_router


class EchoAgent:
    """Provides a small injected agent for endpoint tests."""

    def run(self, user_input: str, session_id: str | None = None) -> str:
        return f"{session_id}:{user_input}"


def test_whatsapp_inbound_endpoint_returns_payload() -> None:
    app = FastAPI()
    app.include_router(create_whatsapp_router(agent=EchoAgent()))
    client = TestClient(app)

    response = client.post(
        "/whatsapp/inbound",
        data={
            "From": "whatsapp:+918895551384",
            "Body": "hello from twilio",
            "To": "whatsapp:+14155238886",
            "MessageSid": "SM123",
            "ProfileName": "Saket",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "response": "whatsapp:+918895551384:hello from twilio",
        "payload": {
            "from": "whatsapp:+918895551384",
            "to": "whatsapp:+14155238886",
            "body": "hello from twilio",
            "message_sid": "SM123",
            "profile_name": "Saket",
        },
    }
