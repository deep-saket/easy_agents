"""Created: 2026-09-24

Purpose: Publishes canonical terms and their temporary technical compatibility names.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TerminologyEntry:
    """Connects one public term to its class and legacy implementation names."""

    term: str
    contract: str
    definition: str
    legacy_names: tuple[str, ...] = ()


TERMINOLOGY: tuple[TerminologyEntry, ...] = (
    TerminologyEntry("Galaxy", "Galaxy", "Top-level ownership and isolation boundary."),
    TerminologyEntry("Circle", "Circle", "Galaxy-owned domain or responsibility group.", ("Guild",)),
    TerminologyEntry("Planet", "Planet", "Autonomous accountable agent.", ("Agent", "Specialist")),
    TerminologyEntry("Rocky Planet", "RockyPlanet", "Narrow specialist Planet.", ("Specialist",)),
    TerminologyEntry("Giant Planet", "GiantPlanet", "Broad coordinating Planet."),
    TerminologyEntry("Component", "Component", "Non-agent Circle Member."),
    TerminologyEntry("Satellite", "Satellite", "Callable tool-backed Component.", ("Tool",)),
    TerminologyEntry("Constellation", "Constellation", "Connected graph overlay across Circle parts."),
    TerminologyEntry("Solar System", "SolarSystem", "Computed one-Planet neighborhood."),
    TerminologyEntry("Wormhole", "Wormhole", "Controlled Mission ingress and router.", ("Gateway",)),
    TerminologyEntry("Rogue Star", "RogueStar", "External shared resource owned by no Galaxy."),
    TerminologyEntry("Orbit", "Orbit", "Typed relationship between entities.", ("Edge",)),
    TerminologyEntry("Mission", "Mission", "User goal submitted through a Wormhole."),
    TerminologyEntry("Trajectory", "Trajectory", "Explainable Mission route.", ("GalaxyRoutePlan",)),
    TerminologyEntry("Crew", "Crew", "Temporary multi-Planet Mission team."),
    TerminologyEntry("Work Order", "WorkOrder", "Bounded delegation to one Planet."),
    TerminologyEntry("Flight Plan", "FlightPlan", "Resolved Playbook steps."),
    TerminologyEntry("Gate", "Gate", "Policy or approval boundary."),
    TerminologyEntry("Roster", "GalaxyRegistry", "Available Planet Charters.", ("FleetRegistry",)),
    TerminologyEntry("Vault", "Vault", "Memory or data-isolation boundary."),
    TerminologyEntry("Observatory", "Observatory", "Monitoring and replay capability."),
    TerminologyEntry("Mission Log", "MissionLog", "Correlated redacted event history."),
    TerminologyEntry("Charter", "Charter", "Planet purpose and maximum authority declaration."),
)
"""Canonical terminology matrix used by documentation and contract tests."""


def terminology_by_term() -> dict[str, TerminologyEntry]:
    """Returns the terminology matrix indexed by canonical display term."""

    return {item.term: item for item in TERMINOLOGY}
