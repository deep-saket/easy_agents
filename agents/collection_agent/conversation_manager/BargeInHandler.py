"""Interruption helpers for text supersession and future voice barge-in."""

from __future__ import annotations

from typing import Any

from agents.collection_agent.conversation_manager.MessageDeliveryTracker import MessageDeliveryTracker


class BargeInHandler:
    """Updates delivery state when active work or delivery is interrupted."""

    def __init__(self, *, delivery_tracker: MessageDeliveryTracker) -> None:
        self._delivery_tracker = delivery_tracker

    def handle_text_supersede(
        self,
        *,
        active_request_id: str,
        new_request_id: str,
    ) -> dict[str, Any]:
        return {
            "interruption_detected": True,
            "interruption_type": "text_latest_input_wins",
            "superseded_request_id": active_request_id,
            "replacement_request_id": new_request_id,
        }

    def handle_voice_barge_in(
        self,
        *,
        message_id: str,
        spoken_ms: float,
        spoken_characters: int,
    ) -> dict[str, Any]:
        record = self._delivery_tracker.interrupt_delivery(
            message_id,
            spoken_ms=spoken_ms,
            spoken_characters=spoken_characters,
        )
        return {
            "interruption_detected": record is not None,
            "interruption_type": "user_barge_in",
            "delivery": record.to_dict() if record is not None else None,
        }
