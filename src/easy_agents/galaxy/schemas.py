"""Created: 2026-09-24

Purpose: Defines versioned public serialization contracts for Galaxy data.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easy_agents.galaxy.circles import Circle
from easy_agents.galaxy.constellations import Constellation
from easy_agents.galaxy.galaxies import Galaxy
from easy_agents.galaxy.members import Component
from easy_agents.galaxy.operations import Gate, Vault
from easy_agents.galaxy.planets import GiantPlanet, RockyPlanet
from easy_agents.galaxy.registry import GalaxyRegistry
from easy_agents.galaxy.rogue_stars import RogueStar
from easy_agents.galaxy.satellites import Satellite


class GalaxySnapshotV2(BaseModel):
    """Portable, deterministic version-2 snapshot of Galaxy domain data.

    Lists are sorted by identifier when built through :meth:`from_registry`.
    Consumers must inspect ``version`` before loading future snapshots.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[2] = 2
    galaxies: tuple[Galaxy, ...]
    circles: tuple[Circle, ...]
    planets: tuple[RockyPlanet | GiantPlanet, ...]
    components: tuple[Satellite | Gate | Vault | Component, ...] = ()
    rogue_stars: tuple[RogueStar, ...] = ()
    constellations: tuple[Constellation, ...] = ()

    @model_validator(mode="after")
    def validate_snapshot(self) -> "GalaxySnapshotV2":
        """Runs full cross-reference validation before accepting a snapshot."""

        GalaxyRegistry(
            galaxies=self.galaxies,
            circles=self.circles,
            planets=self.planets,
            components=tuple(
                item for item in self.components if not isinstance(item, Satellite)
            ),
            satellites=tuple(
                item for item in self.components if isinstance(item, Satellite)
            ),
            rogue_stars=self.rogue_stars,
            constellations=self.constellations,
        )
        return self

    @classmethod
    def from_registry(cls, registry: GalaxyRegistry) -> "GalaxySnapshotV2":
        """Serializes a registry with deterministic entity ordering."""

        return cls(
            galaxies=tuple(registry.galaxies[key] for key in sorted(registry.galaxies)),
            circles=tuple(registry.circles[key] for key in sorted(registry.circles)),
            planets=tuple(registry.planets[key] for key in sorted(registry.planets)),
            components=(
                *(registry.components[key] for key in sorted(registry.components)),
                *(registry.satellites[key] for key in sorted(registry.satellites)),
            ),
            rogue_stars=tuple(
                registry.rogue_stars[key] for key in sorted(registry.rogue_stars)
            ),
            constellations=tuple(
                registry.constellations[key]
                for key in sorted(registry.constellations)
            ),
        )

    def to_registry(self) -> GalaxyRegistry:
        """Rebuilds a validated registry from this snapshot."""

        return GalaxyRegistry(
            galaxies=self.galaxies,
            circles=self.circles,
            planets=self.planets,
            components=tuple(
                item for item in self.components if not isinstance(item, Satellite)
            ),
            satellites=tuple(
                item for item in self.components if isinstance(item, Satellite)
            ),
            rogue_stars=self.rogue_stars,
            constellations=self.constellations,
        )


class TopologyNodeV2(BaseModel):
    """Canonical node exposed by the version-2 topology API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: Literal[
        "galaxy",
        "circle",
        "rocky_planet",
        "giant_planet",
        "component",
        "satellite",
        "rogue_star",
        "constellation",
        "wormhole",
    ]
    label: str
    description: str = ""
    status: str = "available"
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class TopologyOrbitV2(BaseModel):
    """Canonical relationship exposed by the version-2 topology API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source: str
    target: str
    kind: str
    label: str


class GalaxyTopologyV2(BaseModel):
    """Deterministic canonical topology independent of legacy graph kinds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[2] = 2
    nodes: tuple[TopologyNodeV2, ...]
    orbits: tuple[TopologyOrbitV2, ...]
    counts: dict[str, int]

    @model_validator(mode="after")
    def validate_topology(self) -> "GalaxyTopologyV2":
        """Rejects duplicate identifiers, dangling Orbits, and stale counts."""

        node_ids = [item.id for item in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Galaxy topology contains duplicate node identifiers.")
        orbit_ids = [item.id for item in self.orbits]
        if len(orbit_ids) != len(set(orbit_ids)):
            raise ValueError("Galaxy topology contains duplicate Orbit identifiers.")
        known = set(node_ids)
        dangling = sorted(
            endpoint
            for orbit in self.orbits
            for endpoint in (orbit.source, orbit.target)
            if endpoint not in known
        )
        if dangling:
            raise ValueError(
                "Galaxy topology contains dangling Orbit endpoints: "
                + ", ".join(sorted(set(dangling)))
            )
        actual_counts: dict[str, int] = {}
        for node in self.nodes:
            actual_counts[node.kind] = actual_counts.get(node.kind, 0) + 1
        if self.counts != actual_counts:
            raise ValueError("Galaxy topology counts do not match its nodes.")
        return self
