"""Normalize, redact, persist, project, and publish trace events."""

from __future__ import annotations

import os
from pathlib import Path
from threading import RLock
from typing import Any

from easy_agents.observability.contracts import (
    DataClassification,
    EntityReference,
    EventFilter,
    Severity,
    TraceEvent,
)
from easy_agents.observability.hub import LiveEventHub
from easy_agents.observability.normalizer import normalize_legacy_event
from easy_agents.observability.projection import ProjectionEngine
from easy_agents.observability.redaction import EventRedactor
from easy_agents.observability.store import SQLiteEventStore


DEFAULT_DB_PATH = Path("data/observability.db")


class ObservabilityPipeline:
    """Canonical synchronous event sink used by runtimes and the local API."""

    def __init__(
        self,
        *,
        store: SQLiteEventStore,
        redactor: EventRedactor | None = None,
        projector: ProjectionEngine | None = None,
        hub: LiveEventHub | None = None,
    ) -> None:
        self.store = store
        self.redactor = redactor or EventRedactor()
        self.projector = projector or ProjectionEngine()
        self.hub = hub or LiveEventHub()
        self._lock = RLock()
        self.emit_failures = 0
        self._restore_projection()

    @classmethod
    def memory(cls, *, queue_size: int = 256) -> "ObservabilityPipeline":
        """Creates an isolated in-memory pipeline for tests and embedding."""

        return cls(store=SQLiteEventStore.memory(), hub=LiveEventHub(queue_size=queue_size))

    @classmethod
    def default(cls) -> "ObservabilityPipeline":
        """Creates the persistent local Control Room pipeline."""

        configured = os.environ.get("EASY_AGENTS_OBSERVABILITY_DB")
        path = Path(configured).expanduser() if configured else DEFAULT_DB_PATH
        return cls(store=SQLiteEventStore(path))

    def _restore_projection(self) -> None:
        latest = self.store.latest_sequence()
        stored_sequence, records = self.store.load_projections()
        if stored_sequence == latest:
            self.projector.load_records(stored_sequence, records)
            return
        self.rebuild_projections()

    def rebuild_projections(self) -> dict[str, Any]:
        """Rebuilds all read models deterministically from stored events."""

        with self._lock:
            self.projector.reset()
            for event in self.store.iter_all():
                self.projector.apply(event)
            self.store.save_projections(
                self.projector.export_records(),
                last_sequence=self.projector.last_sequence,
                replace=True,
            )
            return self.projector.snapshot()

    def emit(self, event: dict[str, Any]) -> None:
        """Accepts a legacy ``TraceSink`` event without breaking agent runs."""

        try:
            self.publish(normalize_legacy_event(event))
        except Exception:
            self.emit_failures += 1

    def record(
        self,
        event_type: str,
        *,
        summary: str,
        status: str | None = None,
        severity: Severity = Severity.INFO,
        mission_id: str | None = None,
        work_order_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        actor: EntityReference | None = None,
        subject: EntityReference | None = None,
        duration_ms: float | None = None,
        attributes: dict[str, Any] | None = None,
        metrics: dict[str, int | float | None] | None = None,
        data_classification: DataClassification = DataClassification.INTERNAL,
        event_id: str | None = None,
    ) -> TraceEvent:
        """Creates and publishes one canonical event."""

        values: dict[str, Any] = {
            "event_type": event_type,
            "summary": summary,
            "status": status,
            "severity": severity,
            "mission_id": mission_id,
            "work_order_id": work_order_id,
            "run_id": run_id,
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "actor": actor,
            "subject": subject,
            "duration_ms": duration_ms,
            "attributes": attributes or {},
            "metrics": metrics or {},
            "data_classification": data_classification,
        }
        if event_id is not None:
            values["event_id"] = event_id
        return self.publish(TraceEvent(**values))

    def publish(self, event: TraceEvent) -> TraceEvent:
        """Redacts and commits before updating projections and live clients."""

        safe = self.redactor.redact(event)
        with self._lock:
            stored, inserted = self.store.append(safe)
            if not inserted:
                return stored
            changed = self.projector.apply(stored)
            self.store.save_projections(
                changed,
                last_sequence=self.projector.last_sequence,
            )
        self.hub.publish(stored)
        alert = self._derive_alert(stored)
        if alert is not None:
            self.publish(alert)
        return stored

    def _derive_alert(self, event: TraceEvent) -> TraceEvent | None:
        if event.event_type.startswith("alert."):
            return None
        is_failure = event.event_type == "mission.failed"
        is_blocked = event.event_type == "mission.completed" and event.status == "blocked"
        is_waiting = event.event_type == "approval.requested"
        if not (is_failure or is_blocked or is_waiting):
            return None
        if is_waiting:
            summary = "Mission is waiting for approval"
            severity = Severity.WARNING
        elif is_blocked:
            summary = "Mission was blocked by policy"
            severity = Severity.WARNING
        else:
            summary = "Mission failed"
            severity = Severity.ERROR
        return TraceEvent(
            event_id=f"alert-{event.event_id}",
            event_type="alert.opened",
            severity=severity,
            status="open",
            mission_id=event.mission_id,
            work_order_id=event.work_order_id,
            run_id=event.run_id,
            actor=EntityReference(kind="service", id="observability"),
            subject=event.subject or event.actor,
            summary=summary,
            attributes={
                "alert_id": f"alert-{event.event_id}",
                "source_event_id": event.event_id,
            },
        )

    def events(self, filters: EventFilter | None = None) -> list[TraceEvent]:
        """Returns a bounded history page."""

        return self.store.query(filters)

    def snapshot(self) -> dict[str, Any]:
        """Returns current projected state and stream health."""

        payload = self.projector.snapshot()
        payload["recent_events"] = [
            event.model_dump(mode="json") for event in self.store.recent(limit=200)
        ]
        payload["stream"] = self.hub.health()
        payload["store"] = {
            "retained_events": self.store.count(),
            "latest_sequence": self.store.latest_sequence(),
            "emit_failures": self.emit_failures,
        }
        return payload

    def health(self) -> dict[str, Any]:
        """Returns compact store, projection, and stream health."""

        return {
            "status": "ok",
            "latest_sequence": self.store.latest_sequence(),
            "projected_sequence": self.projector.last_sequence,
            "retained_events": self.store.count(),
            "emit_failures": self.emit_failures,
            **self.hub.health(),
        }

    def close(self) -> None:
        """Closes live subscribers and the local database."""

        self.hub.close()
        self.store.close()
