"""Delivery lifecycle tracking for text and future voice responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import threading


@dataclass(slots=True)
class DeliveryRecord:
    """Tracks how much of a message was actually delivered."""

    session_id: str
    message_id: str
    response_id: str
    message_text: str
    delivery_mode: str
    delivery_status: str
    started_at: str
    completed_at: str | None
    interrupted_at: str | None
    spoken_ms: float
    estimated_total_ms: float
    spoken_characters: int
    total_characters: int
    spoken_pct: float
    unspoken_text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class MessageDeliveryTracker:
    """Stores delivery records for replay and barge-in handling."""

    def __init__(self, *, estimated_speech_ms_per_character: float) -> None:
        self._estimated_speech_ms_per_character = max(1.0, float(estimated_speech_ms_per_character))
        self._records: dict[str, DeliveryRecord] = {}
        self._latest_message_id_by_session: dict[str, str] = {}
        self._lock = threading.Lock()

    def start_delivery(
        self,
        *,
        session_id: str,
        message_id: str,
        response_id: str,
        message_text: str,
        delivery_mode: str,
    ) -> DeliveryRecord:
        total_characters = len(message_text)
        estimated_total_ms = max(total_characters * self._estimated_speech_ms_per_character, 1.0)
        record = DeliveryRecord(
            session_id=session_id,
            message_id=message_id,
            response_id=response_id,
            message_text=message_text,
            delivery_mode=delivery_mode,
            delivery_status="started",
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=None,
            interrupted_at=None,
            spoken_ms=0.0,
            estimated_total_ms=estimated_total_ms,
            spoken_characters=0,
            total_characters=total_characters,
            spoken_pct=0.0,
            unspoken_text=message_text,
        )
        with self._lock:
            self._records[message_id] = record
            self._latest_message_id_by_session[session_id] = message_id
        return record

    def complete_delivery(self, message_id: str) -> DeliveryRecord | None:
        with self._lock:
            record = self._records.get(message_id)
            if record is None:
                return None
            record.delivery_status = "delivered"
            record.completed_at = datetime.now(timezone.utc).isoformat()
            record.spoken_ms = record.estimated_total_ms
            record.spoken_characters = record.total_characters
            record.spoken_pct = 1.0
            record.unspoken_text = ""
            return record

    def interrupt_delivery(
        self,
        message_id: str,
        *,
        spoken_ms: float,
        spoken_characters: int,
    ) -> DeliveryRecord | None:
        with self._lock:
            record = self._records.get(message_id)
            if record is None:
                return None
            safe_chars = max(0, min(int(spoken_characters), record.total_characters))
            safe_ms = max(0.0, min(float(spoken_ms), record.estimated_total_ms))
            record.delivery_status = "interrupted"
            record.interrupted_at = datetime.now(timezone.utc).isoformat()
            record.completed_at = None
            record.spoken_ms = safe_ms
            record.spoken_characters = safe_chars
            record.spoken_pct = 0.0 if record.total_characters == 0 else safe_chars / record.total_characters
            record.unspoken_text = record.message_text[safe_chars:]
            return record

    def latest_for_session(self, session_id: str) -> DeliveryRecord | None:
        with self._lock:
            message_id = self._latest_message_id_by_session.get(session_id)
            if not message_id:
                return None
            return self._records.get(message_id)

    def get(self, message_id: str) -> DeliveryRecord | None:
        with self._lock:
            return self._records.get(message_id)

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            latest_message_id = self._latest_message_id_by_session.pop(session_id, None)
            if latest_message_id:
                self._records.pop(latest_message_id, None)
