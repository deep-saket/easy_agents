"""Thread-safe in-process fan-out for durable trace events."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from easy_agents.observability.contracts import TraceEvent


@dataclass(slots=True)
class EventSubscription:
    """One bounded subscriber queue owned by an asyncio event loop."""

    id: str
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[TraceEvent | None]
    closed: bool = False
    close_reason: str | None = None


class LiveEventHub:
    """Publishes committed events without blocking agent execution."""

    def __init__(self, *, queue_size: int = 256) -> None:
        if queue_size < 1:
            raise ValueError("queue_size must be positive")
        self.queue_size = queue_size
        self._lock = RLock()
        self._subscriptions: dict[str, EventSubscription] = {}
        self.published_events = 0
        self.overflow_disconnects = 0

    def subscribe(self) -> EventSubscription:
        """Registers a queue on the caller's running event loop."""

        loop = asyncio.get_running_loop()
        subscription = EventSubscription(
            id=f"subscriber-{uuid4()}",
            loop=loop,
            queue=asyncio.Queue(maxsize=self.queue_size),
        )
        with self._lock:
            self._subscriptions[subscription.id] = subscription
        return subscription

    def unsubscribe(self, subscription: EventSubscription) -> None:
        """Removes a subscriber and marks it closed."""

        with self._lock:
            self._subscriptions.pop(subscription.id, None)
            subscription.closed = True
            subscription.close_reason = subscription.close_reason or "client_closed"

    def publish(self, event: TraceEvent) -> None:
        """Schedules one committed event on every subscriber's loop."""

        with self._lock:
            subscriptions = list(self._subscriptions.values())
            self.published_events += 1
        for subscription in subscriptions:
            try:
                subscription.loop.call_soon_threadsafe(
                    self._enqueue,
                    subscription,
                    event,
                )
            except RuntimeError:
                self.unsubscribe(subscription)

    def _enqueue(self, subscription: EventSubscription, event: TraceEvent) -> None:
        if subscription.closed:
            return
        try:
            subscription.queue.put_nowait(event)
        except asyncio.QueueFull:
            subscription.closed = True
            subscription.close_reason = "overflow"
            self.overflow_disconnects += 1
            while not subscription.queue.empty():
                try:
                    subscription.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            subscription.queue.put_nowait(None)

    def close(self) -> None:
        """Disconnects every subscriber during service shutdown."""

        with self._lock:
            subscriptions = list(self._subscriptions.values())
            self._subscriptions.clear()
        for subscription in subscriptions:
            try:
                subscription.loop.call_soon_threadsafe(self._close_subscription, subscription)
            except RuntimeError:
                subscription.closed = True

    @staticmethod
    def _close_subscription(subscription: EventSubscription) -> None:
        subscription.closed = True
        subscription.close_reason = subscription.close_reason or "server_shutdown"
        if not subscription.queue.full():
            subscription.queue.put_nowait(None)

    def health(self) -> dict[str, int]:
        """Returns stream counters safe for local health responses."""

        with self._lock:
            return {
                "connected_clients": len(self._subscriptions),
                "published_events": self.published_events,
                "overflow_disconnects": self.overflow_disconnects,
                "queue_size": self.queue_size,
            }
