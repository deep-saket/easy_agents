"""Pure current-state projections derived from ordered trace events."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any

from easy_agents.observability.contracts import TraceEvent


_TERMINAL_EVENTS = {
    "mission.completed",
    "mission.failed",
    "mission.cancelled",
    "work_order.completed",
    "work_order.failed",
    "specialist.completed",
    "specialist.failed",
    "playbook.completed",
    "playbook.failed",
    "node.completed",
    "node.failed",
    "tool.completed",
    "tool.failed",
    "model.completed",
    "model.failed",
    "handoff.completed",
    "handoff.rejected",
}


class ProjectionEngine:
    """Maintains Mission, Run, graph-entity, and alert read models."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.last_sequence = 0
        self.missions: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.entities: dict[str, dict[str, Any]] = {}
        self.alerts: dict[str, dict[str, Any]] = {}

    def apply(self, event: TraceEvent) -> list[tuple[str, str, int, dict[str, Any]]]:
        """Applies one event idempotently and returns changed records."""

        sequence = event.sequence or 0
        with self._lock:
            if sequence <= self.last_sequence:
                return []
            changed: list[tuple[str, str, int, dict[str, Any]]] = []
            if event.mission_id:
                mission = self._update_mission(event)
                changed.append(("mission", event.mission_id, sequence, deepcopy(mission)))
            if event.run_id:
                run = self._update_run(event)
                changed.append(("run", event.run_id, sequence, deepcopy(run)))
            seen_entities: set[str] = set()
            for entity in (event.actor, event.subject):
                if entity is None:
                    continue
                key = f"{entity.kind}:{entity.id}"
                if key in seen_entities:
                    continue
                seen_entities.add(key)
                activity = self._update_entity(key, entity.kind, entity.id, event)
                changed.append(("entity", key, sequence, deepcopy(activity)))
            if event.event_type.startswith("alert."):
                alert_key = str(event.attributes.get("alert_id") or event.event_id)
                alert = self._update_alert(alert_key, event)
                changed.append(("alert", alert_key, sequence, deepcopy(alert)))
            self.last_sequence = sequence
            return changed

    def _update_mission(self, event: TraceEvent) -> dict[str, Any]:
        assert event.mission_id is not None
        mission = self.missions.setdefault(
            event.mission_id,
            {
                "mission_id": event.mission_id,
                "status": "created",
                "created_at": event.occurred_at.isoformat(),
                "updated_at": event.occurred_at.isoformat(),
                "finished_at": None,
                "specialist_ids": [],
                "run_ids": [],
                "event_count": 0,
                "error_count": 0,
            },
        )
        mission["event_count"] += 1
        mission["updated_at"] = event.occurred_at.isoformat()
        mission["last_sequence"] = event.sequence
        mission["last_event_type"] = event.event_type
        mission["summary"] = event.summary
        status = _event_status(event)
        if (
            event.event_type.startswith("mission.")
            or event.event_type == "response.composed"
            or status in {"failed", "blocked", "awaiting_approval"}
        ):
            mission["status"] = status
        if event.run_id and event.run_id not in mission["run_ids"]:
            mission["run_ids"].append(event.run_id)
        if event.actor and event.actor.kind == "specialist":
            if event.actor.id not in mission["specialist_ids"]:
                mission["specialist_ids"].append(event.actor.id)
        if event.severity.value in {"error", "critical"}:
            mission["error_count"] += 1
        if event.event_type in {"mission.completed", "mission.failed", "mission.cancelled"}:
            mission["finished_at"] = event.occurred_at.isoformat()
        return mission

    def _update_run(self, event: TraceEvent) -> dict[str, Any]:
        assert event.run_id is not None
        run = self.runs.setdefault(
            event.run_id,
            {
                "run_id": event.run_id,
                "mission_id": event.mission_id,
                "work_order_id": event.work_order_id,
                "status": "created",
                "started_at": None,
                "finished_at": None,
                "event_count": 0,
                "error_count": 0,
                "tool_calls": 0,
                "model_calls": 0,
                "total_tokens": 0,
            },
        )
        run["event_count"] += 1
        run["updated_at"] = event.occurred_at.isoformat()
        run["last_sequence"] = event.sequence
        run["last_event_type"] = event.event_type
        run["summary"] = event.summary
        if event.actor and event.actor.kind == "specialist":
            run["specialist_id"] = event.actor.id
        if event.attributes.get("playbook_id"):
            run["playbook_id"] = event.attributes["playbook_id"]
        event_area = event.event_type.split(".", 1)[0]
        if event_area in {"specialist", "work_order"}:
            run["status"] = _event_status(event)
        elif event.event_type == "approval.requested":
            run["status"] = "awaiting_approval"
        elif event.severity.value in {"error", "critical"}:
            run["status"] = "failed"
        if event.event_type.endswith(".started") and run["started_at"] is None:
            run["started_at"] = event.occurred_at.isoformat()
        if event.event_type in _TERMINAL_EVENTS and event.event_type.startswith("specialist."):
            run["finished_at"] = event.occurred_at.isoformat()
            run["duration_ms"] = event.duration_ms
        if event.event_type.startswith("tool.") and event.event_type in _TERMINAL_EVENTS:
            run["tool_calls"] += 1
        if event.event_type.startswith("model.") and event.event_type in _TERMINAL_EVENTS:
            run["model_calls"] += 1
            tokens = event.metrics.get("total_tokens")
            if isinstance(tokens, (int, float)):
                run["total_tokens"] += int(tokens)
        if event.severity.value in {"error", "critical"}:
            run["error_count"] += 1
        return run

    def _update_entity(
        self,
        key: str,
        kind: str,
        identifier: str,
        event: TraceEvent,
    ) -> dict[str, Any]:
        activity = self.entities.setdefault(
            key,
            {
                "entity_key": key,
                "kind": kind,
                "id": identifier,
                "status": "idle",
                "active_run_ids": [],
                "event_count": 0,
                "error_count": 0,
            },
        )
        active_runs = set(activity["active_run_ids"])
        event_area = event.event_type.split(".", 1)[0]
        if event.run_id and event_area == kind:
            if event.event_type.endswith(".started"):
                active_runs.add(event.run_id)
            if event.event_type in _TERMINAL_EVENTS:
                active_runs.discard(event.run_id)
        activity["active_run_ids"] = sorted(active_runs)
        activity["event_count"] += 1
        activity["last_sequence"] = event.sequence
        activity["last_event_type"] = event.event_type
        activity["updated_at"] = event.occurred_at.isoformat()
        activity["mission_id"] = event.mission_id
        activity["run_id"] = event.run_id
        activity["summary"] = event.summary
        activity["status"] = "running" if active_runs else _event_status(event)
        if event.severity.value in {"error", "critical"}:
            activity["error_count"] += 1
        return activity

    def _update_alert(self, key: str, event: TraceEvent) -> dict[str, Any]:
        alert = self.alerts.setdefault(
            key,
            {"alert_id": key, "opened_at": event.occurred_at.isoformat()},
        )
        alert.update(
            {
                "status": event.event_type.rsplit(".", 1)[-1],
                "severity": event.severity.value,
                "summary": event.summary,
                "last_sequence": event.sequence,
                "updated_at": event.occurred_at.isoformat(),
                "mission_id": event.mission_id,
                "run_id": event.run_id,
            }
        )
        return alert

    def load_records(
        self,
        last_sequence: int,
        records: list[tuple[str, str, dict[str, Any]]],
    ) -> None:
        """Restores a projection snapshot previously persisted by the store."""

        with self._lock:
            self.reset()
            targets = {
                "mission": self.missions,
                "run": self.runs,
                "entity": self.entities,
                "alert": self.alerts,
            }
            for kind, key, payload in records:
                target = targets.get(kind)
                if target is not None:
                    target[key] = deepcopy(payload)
            self.last_sequence = last_sequence

    def reset(self) -> None:
        """Clears every rebuildable projection."""

        with self._lock:
            self.last_sequence = 0
            self.missions.clear()
            self.runs.clear()
            self.entities.clear()
            self.alerts.clear()

    def export_records(self) -> list[tuple[str, str, int, dict[str, Any]]]:
        """Returns every projection record for a durable rebuild checkpoint."""

        with self._lock:
            records: list[tuple[str, str, int, dict[str, Any]]] = []
            for kind, mapping in (
                ("mission", self.missions),
                ("run", self.runs),
                ("entity", self.entities),
                ("alert", self.alerts),
            ):
                records.extend(
                    (kind, key, self.last_sequence, deepcopy(payload))
                    for key, payload in mapping.items()
                )
            return records

    def snapshot(self) -> dict[str, Any]:
        """Returns a stable JSON-ready operations snapshot."""

        with self._lock:
            missions = sorted(
                (deepcopy(item) for item in self.missions.values()),
                key=lambda item: int(item.get("last_sequence") or 0),
                reverse=True,
            )
            runs = sorted(
                (deepcopy(item) for item in self.runs.values()),
                key=lambda item: int(item.get("last_sequence") or 0),
                reverse=True,
            )
            return {
                "last_sequence": self.last_sequence,
                "missions": missions[:100],
                "runs": runs[:250],
                "entities": deepcopy(self.entities),
                "alerts": sorted(
                    (deepcopy(item) for item in self.alerts.values()),
                    key=lambda item: int(item.get("last_sequence") or 0),
                    reverse=True,
                ),
            }

    def mission(self, mission_id: str) -> dict[str, Any] | None:
        """Returns one Mission projection with its Runs."""

        with self._lock:
            mission = self.missions.get(mission_id)
            if mission is None:
                return None
            payload = deepcopy(mission)
            payload["runs"] = [
                deepcopy(run)
                for run in self.runs.values()
                if run.get("mission_id") == mission_id
            ]
            return payload

    def run(self, run_id: str) -> dict[str, Any] | None:
        """Returns one Run projection."""

        with self._lock:
            value = self.runs.get(run_id)
            return deepcopy(value) if value is not None else None

    def metrics(self) -> dict[str, Any]:
        """Derives bounded operational counters from current projections."""

        with self._lock:
            mission_status: dict[str, int] = {}
            for mission in self.missions.values():
                status = str(mission.get("status", "unknown"))
                mission_status[status] = mission_status.get(status, 0) + 1
            active_entities = sum(
                bool(entity.get("active_run_ids")) for entity in self.entities.values()
            )
            return {
                "missions_by_status": mission_status,
                "total_missions": len(self.missions),
                "total_runs": len(self.runs),
                "active_entities": active_entities,
                "open_alerts": sum(
                    alert.get("status") == "opened" for alert in self.alerts.values()
                ),
                "last_sequence": self.last_sequence,
            }


def _event_status(event: TraceEvent) -> str:
    if event.status:
        return event.status
    action = event.event_type.rsplit(".", 1)[-1]
    return {
        "created": "queued",
        "queued": "queued",
        "requested": "waiting",
        "started": "running",
        "completed": "completed",
        "failed": "failed",
        "blocked": "blocked",
        "cancelled": "cancelled",
        "denied": "denied",
        "approved": "approved",
        "allowed": "allowed",
        "waiting": "waiting",
    }.get(action, action)
