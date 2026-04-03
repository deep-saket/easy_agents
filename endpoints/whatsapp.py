"""Created: 2026-04-03

Purpose: Exposes the WhatsApp webhook router and runnable app in one module.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, Form

from agents.simple_conversation import SimpleConversationAgent

def create_whatsapp_router(*, agent: Any) -> APIRouter:
    """Builds a minimal agent-agnostic router for inbound WhatsApp webhooks."""

    router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

    @router.post("/inbound")
    async def inbound(
        From: str = Form(...),
        Body: str = Form(""),
        To: str = Form(""),
        MessageSid: str = Form(""),
        ProfileName: str = Form(""),
    ) -> dict[str, Any]:
        """Handles one inbound Twilio WhatsApp webhook request."""

        payload = {
            "from": From,
            "to": To,
            "body": Body,
            "message_sid": MessageSid,
            "profile_name": ProfileName,
        }
        print("input =", payload)
        response = agent.run(Body, From)
        print("response =", response)
        return {
            "ok": True,
            "response": response,
            "payload": payload,
        }

    return router


def create_app(*, agent: Any | None = None) -> FastAPI:
    """Creates the runnable WhatsApp webhook app.

    Args:
        agent: Optional injected runtime. When omitted, the simple conversation
            agent is constructed from env/config here.

    Returns:
        A FastAPI app exposing the WhatsApp inbound webhook and health route.
    """

    resolved_agent = agent or SimpleConversationAgent.from_env()

    app = FastAPI(title="Standalone WhatsApp Webhook")
    app.include_router(create_whatsapp_router(agent=resolved_agent))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
