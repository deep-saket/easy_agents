"""Buffered response storage for replay and stale-response suppression."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import threading
from typing import Any


@dataclass(slots=True)
class BufferedResponse:
    """Stores one downstream business response plus delivery metadata."""

    session_id: str
    request_id: str
    response_id: str
    message_id: str
    response_target: str
    message_text: str
    created_at: str
    delivery_status: str
    suppressed: bool
    conversation_manager: dict[str, Any]
    delivery: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResponseBuffer:
    """Keeps recent responses for replay, suppression, and debugging."""

    def __init__(self) -> None:
        self._responses_by_session: dict[str, list[BufferedResponse]] = {}
        self._lock = threading.Lock()

    def store(
        self,
        *,
        session_id: str,
        request_id: str,
        response_id: str,
        message_id: str,
        response_target: str,
        message_text: str,
        delivery_status: str,
        suppressed: bool,
        conversation_manager: dict[str, Any],
        delivery: dict[str, Any] | None = None,
    ) -> BufferedResponse:
        record = BufferedResponse(
            session_id=session_id,
            request_id=request_id,
            response_id=response_id,
            message_id=message_id,
            response_target=response_target,
            message_text=message_text,
            created_at=datetime.now(timezone.utc).isoformat(),
            delivery_status=delivery_status,
            suppressed=suppressed,
            conversation_manager=dict(conversation_manager),
            delivery=dict(delivery) if isinstance(delivery, dict) else None,
        )
        with self._lock:
            self._responses_by_session.setdefault(session_id, []).append(record)
        return record

    def latest_replayable(self, session_id: str) -> BufferedResponse | None:
        with self._lock:
            records = list(self._responses_by_session.get(session_id, ()))
        for record in reversed(records):
            if record.suppressed:
                continue
            if record.response_target != "customer":
                continue
            if record.delivery_status in {"delivered", "interrupted", "replayed"}:
                return record
        return None

    def update_delivery(
        self,
        *,
        session_id: str,
        message_id: str,
        delivery_status: str,
        delivery: dict[str, Any],
    ) -> None:
        with self._lock:
            for record in reversed(self._responses_by_session.get(session_id, ())):
                if record.message_id != message_id:
                    continue
                record.delivery_status = delivery_status
                record.delivery = dict(delivery)
                return

    def all_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [record.to_dict() for record in self._responses_by_session.get(session_id, ())]

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._responses_by_session.pop(session_id, None)
