from __future__ import annotations

from dataclasses import dataclass

from mailmind.core.interfaces import Notifier
from mailmind.core.models import NotificationAttempt, NotificationPayload, NotificationStatus


@dataclass(slots=True)
class FakeWhatsAppNotifier(Notifier):
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
    def __init__(self, allowlist: tuple[str, ...]) -> None:
        self._allowlist = allowlist

    def send(self, payload: NotificationPayload) -> NotificationAttempt:
        # TODO: Implement real WhatsApp provider integration with strict allowlist enforcement.
        if self._allowlist and payload.destination not in self._allowlist:
            return NotificationAttempt(
                message_id=payload.message_id,
                channel=payload.channel,
                destination=payload.destination,
                payload=payload.model_dump(mode="json"),
                status=NotificationStatus.FAILED,
                error="Destination is not in the WhatsApp allowlist.",
            )
        raise NotImplementedError("Real WhatsApp integration is not configured in v0.1.")

