"""Configuration for the conversation manager wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ConversationManagerConfig:
    """Defines latency thresholds, filler cadence, and logging behavior."""

    instant_upper_seconds: float = 2.0
    short_wait_seconds: float = 2.0
    medium_wait_seconds: float = 5.0
    long_wait_seconds: float = 10.0
    short_wait_repeat_seconds: float | None = None
    medium_wait_repeat_seconds: float = 4.5
    long_wait_repeat_seconds: float = 8.5
    monitor_poll_seconds: float = 0.2
    filler_enabled: bool = True
    debug_logging: bool = False
    future_voice_settings: dict[str, Any] = field(default_factory=dict)
    interruption_handling_enabled: bool = True
    text_mode_latest_input_wins: bool = True
    suppress_stale_responses: bool = True
    replay_on_repeat_request: bool = True
    repeat_strategy: str = "full_message"
    enable_voice_delivery_tracking: bool = True
    estimated_speech_ms_per_character: float = 45.0
    filler_library_path: Path | None = None
    runtime_dir: Path | None = None

    @classmethod
    def default(cls, *, base_dir: Path) -> "ConversationManagerConfig":
        return cls(
            filler_library_path=(base_dir / "filler_library.json").resolve(),
            runtime_dir=(base_dir / "runtime").resolve(),
        )

    def latency_category(self, elapsed_seconds: float) -> str:
        if elapsed_seconds < self.short_wait_seconds:
            return "instant"
        if elapsed_seconds < self.medium_wait_seconds:
            return "short_wait"
        if elapsed_seconds < self.long_wait_seconds:
            return "medium_wait"
        return "long_wait"

    def repeat_interval_for(self, category: str) -> float | None:
        if category == "short_wait":
            return self.short_wait_repeat_seconds
        if category == "medium_wait":
            return self.medium_wait_repeat_seconds
        if category == "long_wait":
            return self.long_wait_repeat_seconds
        return None
