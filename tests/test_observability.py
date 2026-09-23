"""Contract, privacy, durability, stream, and Fleet tracing tests."""

from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from easy_agents.constellation.api import create_app
from easy_agents.fleet import FleetRuntime, MissionRequest
from easy_agents.observability import (
    EntityReference,
    EventFilter,
    LiveEventHub,
    ObservabilityPipeline,
    SQLiteEventStore,
    TraceEvent,
)


def test_pipeline_redacts_before_storage_and_streaming() -> None:
    pipeline = ObservabilityPipeline.memory()
    secret = "sk-super-secret-123456789"

    event = pipeline.record(
        "tool.failed",
        summary=f"Tool failed with token {secret}",
        status="failed",
        actor=EntityReference(kind="specialist", id="personal_steward"),
        subject=EntityReference(kind="tool", id="email_send"),
        attributes={
            "tool_name": "email_send",
            "error_type": f"AuthorizationError api_key={secret}",
            "tool_arguments": {"recipient": "private@example.com"},
            "unapproved_field": secret,
        },
    )

    stored = pipeline.events()[0]
    serialized = stored.model_dump_json()
    assert event.sequence == 1
    assert secret not in serialized
    assert "[redacted]" in serialized
    assert "tool_arguments" not in stored.attributes
    assert "unapproved_field" not in stored.attributes


def test_event_ids_are_idempotent_and_sequences_are_monotonic() -> None:
    pipeline = ObservabilityPipeline.memory()
    first = pipeline.record(
        "mission.created",
        event_id="evt-fixed",
        summary="Mission created",
        status="queued",
        mission_id="mission-one",
    )
    duplicate = pipeline.record(
        "mission.created",
        event_id="evt-fixed",
        summary="This duplicate must not replace the original",
        status="queued",
        mission_id="mission-one",
    )
    second = pipeline.record(
        "mission.started",
        summary="Mission started",
        status="running",
        mission_id="mission-one",
    )

    assert first.sequence == duplicate.sequence == 1
    assert duplicate.summary == "Mission created"
    assert second.sequence == 2
    assert pipeline.store.count() == 2


def test_projection_restores_and_rebuilds_from_sqlite(tmp_path) -> None:
    database = tmp_path / "observability.db"
    first = ObservabilityPipeline(store=SQLiteEventStore(database))
    first.record(
        "mission.created",
        summary="Mission created",
        status="queued",
        mission_id="mission-one",
    )
    first.record(
        "mission.completed",
        summary="Mission completed",
        status="completed",
        mission_id="mission-one",
    )
    first.close()

    restored = ObservabilityPipeline(store=SQLiteEventStore(database))
    assert restored.snapshot()["missions"][0]["status"] == "completed"
    assert restored.snapshot()["last_sequence"] == 2

    restored.store.save_projections([], last_sequence=0, replace=True)
    rebuilt = restored.rebuild_projections()
    assert rebuilt["last_sequence"] == 2
    assert rebuilt["missions"][0]["status"] == "completed"


def test_fleet_emits_a_complete_correlated_mission_tree() -> None:
    pipeline = ObservabilityPipeline.memory()
    runtime = FleetRuntime(event_recorder=pipeline)

    result = runtime.run(
        MissionRequest(
            objective="calculate a satellite RF link budget",
            specialist_id="rf_link_budget_specialist",
        )
    )

    events = pipeline.events(EventFilter(mission_id=result.mission_id, limit=2_000))
    event_types = [event.event_type for event in events]
    run_ids = {event.run_id for event in events if event.run_id}
    assert event_types[0:3] == ["mission.created", "mission.routed", "mission.started"]
    assert "work_order.created" in event_types
    assert "specialist.selected" in event_types
    assert "specialist.started" in event_types
    assert "policy.allowed" in event_types
    assert "playbook.started" in event_types
    assert "playbook.completed" in event_types
    assert event_types[-1] == "mission.completed"
    assert len(run_ids) == 1
    assert all(event.mission_id == result.mission_id for event in events)

    snapshot = pipeline.snapshot()
    assert snapshot["missions"][0]["status"] == "planned"
    assert snapshot["runs"][0]["status"] == "planned"
    specialist = snapshot["entities"]["specialist:rf_link_budget_specialist"]
    assert specialist["active_run_ids"] == []


def test_approval_and_model_failure_are_visible_without_raw_content() -> None:
    class FailingModel:
        model_name = "private-model"

        def generate(self, system_prompt: str, user_prompt: str) -> str:
            raise RuntimeError("provider failed with password=do-not-store")

    approval_pipeline = ObservabilityPipeline.memory()
    approval_runtime = FleetRuntime(event_recorder=approval_pipeline)
    approval = approval_runtime.run(
        MissionRequest(
            objective="Call mom this evening.",
            specialist_id="family_relationships_specialist",
        )
    )
    approval_events = approval_pipeline.events(
        EventFilter(mission_id=approval.mission_id, limit=2_000)
    )
    assert "approval.requested" in {event.event_type for event in approval_events}
    assert "alert.opened" in {event.event_type for event in approval_events}
    assert approval_pipeline.snapshot()["missions"][0]["status"] == "awaiting_approval"

    failure_pipeline = ObservabilityPipeline.memory()
    failed = FleetRuntime(llm=FailingModel(), event_recorder=failure_pipeline).run(
        MissionRequest(
            objective="Make a bounded daily plan.",
            specialist_id="personal_steward",
        )
    )
    serialized = json.dumps(failure_pipeline.snapshot()) + json.dumps(
        [event.model_dump(mode="json") for event in failure_pipeline.events()]
    )
    assert failed.status.value == "failed"
    assert "model.failed" in {event.event_type for event in failure_pipeline.events()}
    assert "do-not-store" not in serialized


def test_operations_api_supports_snapshot_history_replay_and_sse() -> None:
    pipeline = ObservabilityPipeline.memory()
    client = TestClient(create_app(observability=pipeline))
    response = client.post(
        "/api/missions/run",
        json={
            "objective": "make a daily plan with secret sk-hidden-123456789",
            "specialist_id": "personal_steward",
        },
    )
    mission_id = response.json()["mission_id"]

    snapshot = client.get("/api/operations/snapshot")
    history = client.get("/api/events", params={"mission_id": mission_id})
    mission = client.get(f"/api/missions/{mission_id}")
    timeline = client.get(f"/api/missions/{mission_id}/timeline")
    metrics = client.get("/api/metrics/summary")
    stream = client.get(
        "/api/events/stream",
        params={"after_sequence": 1, "limit": 1},
        headers={"Last-Event-ID": "1"},
    )

    assert response.status_code == 200
    assert snapshot.status_code == 200
    assert snapshot.json()["recent_events"]
    assert history.status_code == 200
    assert history.json()["events"][0]["mission_id"] == mission_id
    assert "sk-hidden-123456789" not in history.text
    assert mission.status_code == 200
    assert mission.json()["runs"]
    assert timeline.status_code == 200
    assert timeline.json()["events"][-1]["event_type"] == "mission.completed"
    assert metrics.json()["total_missions"] == 1
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "id: 2" in stream.text


def test_legacy_trace_sink_normalizes_and_discards_raw_state() -> None:
    pipeline = ObservabilityPipeline.memory()
    pipeline.emit(
        {
            "event": "node_state",
            "trace_id": "trace-one",
            "node_name": "respond",
            "state": {
                "response": "private answer",
                "route": "respond",
                "memory_context_keys": ["preferences"],
            },
            "user_input": "private request",
        }
    )

    event = pipeline.events()[0]
    assert event.event_type == "node.state_changed"
    assert event.attributes == {
        "node_name": "respond",
        "route": "respond",
        "memory_context_keys": ["preferences"],
    }
    assert "private answer" not in event.model_dump_json()
    assert "private request" not in event.model_dump_json()


def test_slow_live_subscriber_is_disconnected_and_can_catch_up() -> None:
    async def scenario() -> None:
        hub = LiveEventHub(queue_size=1)
        subscription = hub.subscribe()
        hub.publish(TraceEvent(event_type="mission.created", summary="one"))
        hub.publish(TraceEvent(event_type="mission.started", summary="two"))
        await asyncio.sleep(0)
        assert subscription.closed is True
        assert subscription.close_reason == "overflow"
        assert hub.health()["overflow_disconnects"] == 1

    asyncio.run(scenario())
