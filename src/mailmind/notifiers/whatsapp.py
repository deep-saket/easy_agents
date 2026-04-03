"""Created: 2026-03-30

Purpose: Implements the whatsapp module for the shared mailmind platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.interfaces.whatsapp import TwilioWhatsAppInterface
from src.mailmind.core.interfaces import Notifier
from src.mailmind.core.models import NotificationAttempt, NotificationPayload, NotificationStatus


@dataclass(slots=True)
class FakeWhatsAppNotifier(Notifier):
    """Represents the fake whats app notifier component."""
    allowlist: tuple[str, ...]

    def send(self, payload: NotificationPayload) -> NotificationAttempt:
        allowed = not self.allowlist or payload.destination in self.allowlist
        return NotificationAttempt(
            message_id=payload.message_id,
            channel=payload.channel,
            destination=payload.destination,
            payload=payload.model_dump(mode="json"),
            status=NotificationStatus.SENT if allowed else NotificationStatus.FAILED,
            error=None if allowed else "Destination is not in the WhatsApp allowlist.",
        )


class WhatsAppNotifier(Notifier):
    """Represents the whats app notifier component."""
    def __init__(
        self,
        allowlist: tuple[str, ...],
        *,
        account_sid: str,
        auth_token: str,
        whatsapp_from: str,
        interface: TwilioWhatsAppInterface | None = None,
    ) -> None:
        self._allowlist = allowlist
        self._interface = interface or TwilioWhatsAppInterface(
            account_sid=account_sid,
            auth_token=auth_token,
            whatsapp_from=whatsapp_from,
        )

    def send(self, payload: NotificationPayload) -> NotificationAttempt:
        if self._allowlist and payload.destination not in self._allowlist:
            return NotificationAttempt(
                message_id=payload.message_id,
                channel=payload.channel,
                destination=payload.destination,
                payload=payload.model_dump(mode="json"),
                status=NotificationStatus.FAILED,
                error="Destination is not in the WhatsApp allowlist.",
            )
        try:
            self._interface.send_message(payload.destination, payload.body)
        except Exception as exc:
            return NotificationAttempt(
                message_id=payload.message_id,
                channel=payload.channel,
                destination=payload.destination,
                payload=payload.model_dump(mode="json"),
                status=NotificationStatus.FAILED,
                error=str(exc),
            )
        return NotificationAttempt(
            message_id=payload.message_id,
            channel=payload.channel,
            destination=payload.destination,
            payload=payload.model_dump(mode="json"),
            status=NotificationStatus.SENT,
            error=None,
        )
