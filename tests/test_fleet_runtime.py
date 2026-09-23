"""Contract tests for the declarative 70-Specialist fleet runtime."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from easy_agents.constellation import ConstellationDirectory
from easy_agents.constellation.api import create_app
from easy_agents.fleet import (
    MAC_GEMMA_PROFILE_ID,
    FleetRegistry,
    FleetRuntime,
    MissionRequest,
    MissionStatus,
    SpecialistStatus,
)
from easy_agents.fleet.cli import main as fleet_cli_main
from easy_agents.fleet.model_profiles import build_fleet_mac_gemma
from easy_agents.observability import EventFilter, ObservabilityPipeline


class FakeLocalModel:
    """Small deterministic model double for Specialist prompt tests."""

    model_name = "fake-local-model"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return "Evidence is incomplete. Next action: validate the highest-risk assumption."


class FakeGemmaModel(FakeLocalModel):
    """Ready external-service double for API model selection tests."""

    model_name = "gemma-4-E4B"
    base_url = "http://127.0.0.1:8080"

    @staticmethod
    def is_ready() -> bool:
        return True

    @staticmethod
    def list_models() -> list[str]:
        return ["gemma-4-E4B"]


class EmptyLocalModel(FakeGemmaModel):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return "\n\n"


def test_registry_compiles_the_complete_roster_from_shared_components() -> None:
    registry = FleetRegistry.default()

    assert registry.summary() == {
        "specialists": 70,
        "active": 14,
        "sandboxed": 56,
        "playbooks": 9,
        "policies": 4,
        "memory_scopes": 6,
    }
    assert registry.get_specialist("personal_steward").status == SpecialistStatus.ACTIVE
    assert (
        registry.get_specialist("rf_link_budget_specialist").status
        == SpecialistStatus.SANDBOXED
    )
    assert "analyze_and_compare" in registry.get_specialist(
        "rf_link_budget_specialist"
    ).playbook_ids
    assert "exploration" in registry.get_specialist(
        "clinical_evidence_specialist"
    ).memory_scope_ids
    assert "medical_safety" in registry.get_specialist(
        "clinical_evidence_specialist"
    ).policy_ids


def test_every_specialist_is_instantiable_and_runnable_in_safe_mode() -> None:
    registry = FleetRegistry.default()
    runtime = FleetRuntime(registry=registry)

    results = [
        runtime.run(
            MissionRequest(
                objective="Prepare a bounded advisory brief from the supplied local context.",
                specialist_id=manifest.id,
            )
        )
        for manifest in registry.list_specialists()
    ]

    assert len(results) == 70
    assert all(len(result.results) == 1 for result in results)
    assert all(result.status == MissionStatus.PLANNED for result in results)
    assert {
        result.results[0].specialist_id for result in results
    } == set(registry.specialists)
    assert all(result.results[0].steps for result in results)


def test_router_selects_domain_specialists_without_starting_models() -> None:
    registry = FleetRegistry.default()

    cases = {
        "calculate a satellite RF link budget": "rf_link_budget_specialist",
        "review clinical evidence for a medical device": "clinical_evidence_specialist",
        "plan groceries and pantry restocking": "shopping_pantry_specialist",
        "call mom this evening": "family_relationships_specialist",
        "make a daily plan": "personal_steward",
        "do household chores": "household_operator",
        "brainstorm startup ideas": "idea_lab",
    }
    for objective, expected in cases.items():
        assert registry.route(objective, limit=1)[0].specialist_id == expected


def test_memory_scopes_are_isolated_between_employment_and_exploration() -> None:
    runtime = FleetRuntime()

    allowed = runtime.run(
        MissionRequest(
            objective="Review the supplied authorized work note for confidentiality concerns.",
            specialist_id="employment_boundary_guardian",
            memory_scope="employer_authorized",
        )
    )
    blocked = runtime.run(
        MissionRequest(
            objective="Use work material to evaluate an independent battery startup thesis.",
            specialist_id="energy_systems_scout",
            memory_scope="employer_authorized",
        )
    )

    assert allowed.status == MissionStatus.PLANNED
    assert blocked.status == MissionStatus.BLOCKED
    assert "cannot access memory scope" in blocked.warnings[0]


def test_medical_authority_and_external_network_are_denied() -> None:
    runtime = FleetRuntime()

    medical = runtime.run(
        MissionRequest(
            objective="Diagnose me and prescribe a treatment from these symptoms.",
            specialist_id="clinical_evidence_specialist",
        )
    )
    network = runtime.run(
        MissionRequest(
            objective="Research current battery suppliers on the public internet.",
            specialist_id="energy_materials_scout",
            allow_network=True,
        )
    )

    assert medical.status == MissionStatus.BLOCKED
    assert "diagnose" in " ".join(medical.warnings).lower()
    assert network.status == MissionStatus.BLOCKED
    assert "network" in " ".join(network.warnings).lower()


def test_outbound_call_stops_at_gate_until_explicitly_approved() -> None:
    runtime = FleetRuntime()
    pending = runtime.run(
        MissionRequest(
            objective="Call mom this evening.",
            specialist_id="family_relationships_specialist",
        )
    )
    approved = runtime.run(
        MissionRequest(
            objective="Call mom this evening.",
            specialist_id="family_relationships_specialist",
            approved_effects=["call"],
        )
    )

    assert pending.status == MissionStatus.AWAITING_APPROVAL
    assert pending.results[0].approvals[0].effects == ["call"]
    assert approved.status == MissionStatus.PLANNED
    assert approved.results[0].approvals == []


def test_local_model_receives_charter_playbook_and_policy_context() -> None:
    model = FakeLocalModel()
    runtime = FleetRuntime(llm=model)

    result = runtime.run(
        MissionRequest(
            objective="Compare two local battery-storage concepts using supplied data.",
            specialist_id="electrochemistry_storage_specialist",
        )
    )

    assert result.status == MissionStatus.COMPLETED
    assert result.results[0].used_model == "fake-local-model"
    assert "Electrochemistry & Storage Specialist" in model.calls[0][0]
    assert "Policies:" in model.calls[0][0]
    assert "Mission:" in model.calls[0][1]


def test_empty_model_completion_fails_instead_of_claiming_success() -> None:
    model = EmptyLocalModel()
    operations = ObservabilityPipeline.memory()
    runtime = FleetRuntime(
        models={MAC_GEMMA_PROFILE_ID: model},
        event_recorder=operations,
    )

    result = runtime.run(
        MissionRequest(
            objective="Compare two supplied storage concepts.",
            specialist_id="energy_systems_scout",
            model_id=MAC_GEMMA_PROFILE_ID,
        )
    )

    assert result.status == MissionStatus.FAILED
    assert result.results[0].used_model == "gemma-4-E4B"
    assert "empty completion" in " ".join(result.warnings)
    assert "model.failed" in {
        event.event_type
        for event in operations.events(EventFilter(mission_id=result.mission_id, limit=200))
    }


def test_team_run_creates_permission_bounded_work_orders() -> None:
    runtime = FleetRuntime()

    result = runtime.run(
        MissionRequest(
            objective="Compare battery storage opportunities and challenge the scientific evidence.",
            team_size=3,
        )
    )

    assert len(result.routed_specialists) == 3
    assert len(result.results) == 3
    assert len({item.work_order.id for item in result.results}) == 3
    for item in result.results:
        manifest = runtime.registry.get_specialist(item.specialist_id)
        assert set(item.work_order.permissions.memory_scopes) <= set(
            manifest.memory_scope_ids
        )


def test_fleet_validation_exercises_every_specialist_in_one_traced_mission() -> None:
    operations = ObservabilityPipeline.memory()
    runtime = FleetRuntime(event_recorder=operations)

    report = runtime.validate_all()

    assert report.status == "passed"
    assert report.tested_count == 70
    assert report.passed_count == 70
    assert report.failed_count == 0
    assert len(report.results) == 70
    assert {item.specialist_id for item in report.results} == set(
        runtime.registry.specialists
    )
    assert all(item.passed and item.outcome == MissionStatus.PLANNED for item in report.results)

    events = operations.events(
        EventFilter(mission_id=report.mission_id, limit=2_000)
    )
    assert events[0].event_type == "mission.created"
    assert "fleet_validation.started" in {event.event_type for event in events}
    assert "fleet_validation.completed" in {event.event_type for event in events}
    assert events[-1].event_type == "mission.completed"
    assert len({event.run_id for event in events if event.run_id}) == 70


def test_fleet_api_lists_routes_inspects_and_runs_agents() -> None:
    client = TestClient(create_app())

    fleet = client.get("/api/fleet")
    specialist = client.get("/api/fleet/rf_link_budget_specialist")
    route = client.post(
        "/api/missions/route",
        json={"objective": "calculate a satellite RF link budget"},
    )
    run = client.post(
        "/api/missions/run",
        json={
            "objective": "calculate a satellite RF link budget",
            "specialist_id": "rf_link_budget_specialist",
        },
    )
    validation = client.post("/api/fleet/test")

    assert fleet.status_code == 200
    assert fleet.json()["summary"]["specialists"] == 70
    assert specialist.status_code == 200
    assert specialist.json()["status"] == "sandboxed"
    assert route.status_code == 200
    assert route.json()["candidates"][0]["specialist_id"] == "rf_link_budget_specialist"
    assert run.status_code == 200
    assert run.json()["status"] == "planned"
    assert validation.status_code == 200
    assert validation.json()["status"] == "passed"
    assert validation.json()["tested_count"] == 70


def test_fleet_api_reports_and_uses_external_mac_gemma() -> None:
    model = FakeGemmaModel()
    client = TestClient(create_app(gemma_client=model))

    status = client.get("/api/models/mac-gemma/status")
    run = client.post(
        "/api/missions/run",
        json={
            "objective": "Compare two supplied storage concepts.",
            "specialist_id": "energy_systems_scout",
            "model_id": MAC_GEMMA_PROFILE_ID,
        },
    )

    assert status.status_code == 200
    assert status.json()["ready"] is True
    assert status.json()["models"] == ["gemma-4-E4B"]
    assert status.json()["external_service"] is True
    assert run.status_code == 200
    assert run.json()["status"] == "completed"
    assert run.json()["results"][0]["used_model"] == "gemma-4-E4B"
    assert model.calls
    assert model.calls[0][0] == ""
    assert model.calls[0][1].endswith(
        'Energy Systems Scout assessment of the Mission "Compare two supplied '
        'storage concepts.": '
    )


def test_fleet_mac_gemma_profile_uses_environment_and_no_blank_line_stop(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GEMMA_API_BASE", "http://127.0.0.1:18091")
    monkeypatch.setenv("EASY_AGENT_LLM_MAX_NEW_TOKENS", "96")
    monkeypatch.setenv("EASY_AGENT_LLM_TEMPERATURE", "0.3")

    client = build_fleet_mac_gemma()

    assert client.base_url == "http://127.0.0.1:18091"
    assert client.max_tokens == 96
    assert client.temperature == 0.3
    assert client.stop == ()


def test_custom_constellation_api_compiles_only_its_own_specialists() -> None:
    directory = ConstellationDirectory.from_mapping(
        {
            "version": 1,
            "guilds": [
                {
                    "id": "commons",
                    "display_name": "Commons",
                    "purpose": "Shared local work.",
                }
            ],
            "capabilities": [
                {
                    "id": "coordination.route",
                    "display_name": "Route",
                    "description": "Route local work.",
                }
            ],
            "specialists": [
                {
                    "id": "custom_steward",
                    "display_name": "Custom Steward",
                    "purpose": "Handle a private custom roster.",
                    "guilds": ["commons"],
                    "capability_ids": ["coordination.route"],
                }
            ],
        }
    )
    client = TestClient(create_app(directory))

    response = client.get("/api/fleet")

    assert response.status_code == 200
    assert response.json()["summary"]["specialists"] == 1
    assert response.json()["specialists"][0]["id"] == "custom_steward"


def test_cli_lists_and_routes_the_same_registry(capsys) -> None:
    assert fleet_cli_main(["--compact", "list", "--status", "sandboxed"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert len(listed["specialists"]) == 56

    assert fleet_cli_main(
        ["--compact", "route", "calculate", "a", "satellite", "link", "budget"]
    ) == 0
    routed = json.loads(capsys.readouterr().out)
    assert routed["candidates"][0]["specialist_id"] == "rf_link_budget_specialist"
