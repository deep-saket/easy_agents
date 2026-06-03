"""Timer-based latency monitoring and filler emission."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

from agents.collection_agent.conversation_manager.ConversationManagerConfig import ConversationManagerConfig
from agents.collection_agent.conversation_manager.FillerManager import FillerManager


@dataclass(slots=True)
class FillerEmission:
    """Describes one emitted filler event."""

    category: str
    text: str
    elapsed_seconds: float
    sequence: int


class LatencyMonitor:
    """Polls elapsed time and emits fillers according to configured thresholds."""

    def __init__(
        self,
        *,
        config: ConversationManagerConfig,
        filler_manager: FillerManager,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._filler_manager = filler_manager
        self._clock = clock or time.monotonic
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._done_event: threading.Event | None = None
        self._started_at = 0.0
        self._sequence = 0
        self._last_emitted_at: dict[str, float] = {}

    def start(
        self,
        *,
        done_event: threading.Event,
        cancel_event: threading.Event | None = None,
        on_emit: Callable[[FillerEmission], None],
    ) -> None:
        self._done_event = done_event
        self._stop_event.clear()
        self._started_at = self._clock()
        self._sequence = 0
        self._last_emitted_at = {}
        self._thread = threading.Thread(target=self._run, args=(cancel_event, on_emit), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None

    def _run(
        self,
        cancel_event: threading.Event | None,
        on_emit: Callable[[FillerEmission], None],
    ) -> None:
        while not self._stop_event.is_set():
            if cancel_event is not None and cancel_event.is_set():
                return
            if self._done_event is not None and self._done_event.is_set():
                return
            elapsed = self._clock() - self._started_at
            category = self._config.latency_category(elapsed)
            if category != "instant" and self._should_emit(category, elapsed):
                text = self._filler_manager.next_message(category)
                if text:
                    self._sequence += 1
                    self._last_emitted_at[category] = elapsed
                    on_emit(
                        FillerEmission(
                            category=category,
                            text=text,
                            elapsed_seconds=elapsed,
                            sequence=self._sequence,
                        )
                    )
            if self._done_event is not None and self._done_event.wait(self._config.monitor_poll_seconds):
                return

    def _should_emit(self, category: str, elapsed_seconds: float) -> bool:
        if category not in self._last_emitted_at:
            return True
        repeat_interval = self._config.repeat_interval_for(category)
        if repeat_interval is None:
            return False
        return (elapsed_seconds - self._last_emitted_at[category]) >= repeat_interval
