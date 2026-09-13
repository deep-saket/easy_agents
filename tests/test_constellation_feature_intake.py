"""Tests for the offline constellation directory and Feature Architect."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from easy_agents.constellation import (
    ConstellationDirectory,
    FeatureDecision,
    FeatureIntakeService,
    LifecycleStatus,
    RiskLevel,
)
from easy_agents.constellation.api import create_app


@pytest.fixture()
def service() -> FeatureIntakeService:
    return FeatureIntakeService(ConstellationDirectory.default())


def test_default_directory_has_cross_guild_liaisons() -> None:
    directory = ConstellationDirectory.default()

    steward = directory.specialists["personal_steward"]
    safety = directory.specialists["safety_steward"]

    assert steward.liaison is True
    assert {"home", "science_lab", "venture_studio"}.issubset(steward.guilds)
    assert safety.liaison is True
    assert set(safety.guilds) == set(directory.guilds)


def test_reuses_an_existing_research_capability(service: FeatureIntakeService) -> None:
    proposal = service.assess("Summarize three machine learning research papers")

    assert proposal.decision is FeatureDecision.REUSE
    assert proposal.inferred_guilds[0] == "science_lab"
    assert proposal.matched_specialists[0].id == "knowledge_librarian"
    assert proposal.matched_capabilities[0].id == "knowledge.summarize"
    assert proposal.requires_human_approval is False


def test_composes_a_playbook_for_household_tracking_and_reminders(
    service: FeatureIntakeService,
) -> None:
    proposal = service.assess(
        "Track my household electricity bill and remind me before the due date"
    )

    assert proposal.decision is FeatureDecision.COMPOSE
    assert {"home", "life_admin"}.issubset(proposal.inferred_guilds)
    assert {"household_operator", "schedule_coordinator"}.issubset(
        {match.id for match in proposal.matched_specialists}
    )
    assert proposal.missing_capabilities == []


def test_extends_a_domain_specialist_when_the_required_effect_is_missing(
    service: FeatureIntakeService,
) -> None:
    proposal = service.assess("Pay my electricity bill")

    assert proposal.decision is FeatureDecision.EXTEND
    assert proposal.risk is RiskLevel.CRITICAL
    assert proposal.requires_human_approval is True
    assert any(item.endswith(".payment") for item in proposal.missing_capabilities)
    assert proposal.safe_to_auto_scaffold is False


def test_creates_only_a_proposed_charter_for_a_new_domain(
    service: FeatureIntakeService,
) -> None:
    proposal = service.assess("Manage a hydroponic farm nutrient pump")

    assert proposal.decision is FeatureDecision.CREATE
    assert proposal.draft_charter is not None
    assert proposal.draft_charter.status is LifecycleStatus.PROPOSED
    assert proposal.draft_charter.requested_permissions == []
    assert proposal.safe_to_auto_scaffold is True


def test_sensitive_identity_work_requires_approval(service: FeatureIntakeService) -> None:
    proposal = service.assess("Create an Aadhaar renewal reminder")

    assert proposal.requires_human_approval is True
    assert proposal.matched_capabilities[0].id == "government.track_documents"


def test_outbound_communication_requires_approval(
    service: FeatureIntakeService,
) -> None:
    proposal = service.assess("Send an investor update email")

    assert proposal.decision is FeatureDecision.REUSE
    assert proposal.requires_human_approval is True
    assert "send" in proposal.requested_effects


def test_reading_email_does_not_inherit_send_approval(
    service: FeatureIntakeService,
) -> None:
    proposal = service.assess("Summarize my email thread")

    assert proposal.decision is FeatureDecision.REUSE
    assert proposal.requested_effects == ["read"]
    assert proposal.requires_human_approval is False


def test_travel_research_reports_its_network_requirement(
    service: FeatureIntakeService,
) -> None:
    proposal = service.assess("Plan an IRCTC train trip to Delhi")

    assert proposal.decision is FeatureDecision.REUSE
    assert proposal.matched_capabilities[0].id == "travel.plan"
    assert proposal.network_required is True


def test_directory_rejects_dangling_capability_references() -> None:
    with pytest.raises(ValidationError, match="unknown capabilities"):
        ConstellationDirectory.from_mapping(
            {
                "version": 1,
                "guilds": [
                    {
                        "id": "commons",
                        "display_name": "Commons",
                        "purpose": "Shared work",
                    }
                ],
                "capabilities": [],
                "specialists": [
                    {
                        "id": "broken_specialist",
                        "display_name": "Broken Specialist",
                        "purpose": "Invalid fixture",
                        "guilds": ["commons"],
                        "capability_ids": ["missing.capability"],
                    }
                ],
            }
        )


def test_proposed_specialists_are_not_selected() -> None:
    directory = ConstellationDirectory.default()
    directory.specialists["travel_coordinator"].status = LifecycleStatus.PROPOSED

    proposal = FeatureIntakeService(directory).assess("IRCTC hotel flight")

    assert proposal.decision is FeatureDecision.CREATE
    assert "travel_coordinator" not in {
        match.id for match in proposal.matched_specialists
    }


def test_feature_proposal_is_deterministic(service: FeatureIntakeService) -> None:
    first = service.assess("Compare startup competitors")
    second = service.assess("Compare startup competitors")

    assert first.proposal_id == second.proposal_id
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_constellation_api_exposes_health_and_roster() -> None:
    client = TestClient(create_app())

    health = client.get("/health")
    roster = client.get("/api/constellation")

    assert health.status_code == 200
    assert health.json()["specialists"] == 16
    assert roster.status_code == 200
    assert roster.json()["version"] == 1
    assert len(roster.json()["guilds"]) == 9


def test_constellation_api_assesses_feature_requests() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/features/assess",
        json={"feature": "Pay my electricity bill"},
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "extend_specialist"
    assert response.json()["risk"] == "critical"
    assert response.json()["requires_human_approval"] is True
