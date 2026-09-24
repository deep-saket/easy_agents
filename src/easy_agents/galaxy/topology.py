"""Created: 2026-09-24

Purpose: Projects a canonical GalaxyRegistry into a version-2 topology graph.
"""

from __future__ import annotations

from collections import Counter

from easy_agents.galaxy.enums import EntityKind
from easy_agents.galaxy.planets import RockyPlanet
from easy_agents.galaxy.registry import GalaxyRegistry
from easy_agents.galaxy.schemas import GalaxyTopologyV2, TopologyNodeV2, TopologyOrbitV2


def build_topology(registry: GalaxyRegistry) -> GalaxyTopologyV2:
    """Builds deterministic canonical nodes and Orbits from a registry.

    Args:
        registry: Fully validated canonical registry.

    Returns:
        Version-2 topology suitable for APIs, documentation tools, and future
        Control Room migration.
    """

    nodes: list[TopologyNodeV2] = []
    orbits: list[TopologyOrbitV2] = []

    nodes.append(
        TopologyNodeV2(
            id="wormhole:wormhole",
            kind="wormhole",
            label="Wormhole",
            description="The controlled entry point that routes Missions into a Galaxy.",
            status="active",
        )
    )

    for galaxy in registry.galaxies.values():
        nodes.append(
            TopologyNodeV2(
                id=f"galaxy:{galaxy.id}",
                kind="galaxy",
                label=galaxy.display_name,
                description=galaxy.description,
                status="active",
                metadata={"default": galaxy.default},
            )
        )
        orbits.append(
            TopologyOrbitV2(
                id=f"enters:wormhole:wormhole->galaxy:{galaxy.id}",
                source="wormhole:wormhole",
                target=f"galaxy:{galaxy.id}",
                kind="enters",
                label="enters Galaxy",
            )
        )
        for circle_id in galaxy.circle_ids:
            orbits.append(
                TopologyOrbitV2(
                    id=f"contains:galaxy:{galaxy.id}->circle:{circle_id}",
                    source=f"galaxy:{galaxy.id}",
                    target=f"circle:{circle_id}",
                    kind="contains",
                    label="contains Circle",
                )
            )
        for access in galaxy.external_access:
            orbits.append(
                TopologyOrbitV2(
                    id=f"accesses:galaxy:{galaxy.id}->rogue_star:{access.rogue_star_id}",
                    source=f"galaxy:{galaxy.id}",
                    target=f"rogue_star:{access.rogue_star_id}",
                    kind="accesses_external",
                    label="accesses Rogue Star",
                )
            )

    for circle in registry.circles.values():
        nodes.append(
            TopologyNodeV2(
                id=f"circle:{circle.id}",
                kind="circle",
                label=circle.display_name,
                description=circle.purpose,
                status="active",
            )
        )
        for member in circle.members:
            target = _topology_id(member.kind, member.id)
            orbits.append(
                TopologyOrbitV2(
                    id=f"member:circle:{circle.id}->{target}",
                    source=f"circle:{circle.id}",
                    target=target,
                    kind="has_member",
                    label="contains Circle Member",
                )
            )

    for planet in registry.planets.values():
        kind = "rocky_planet" if isinstance(planet, RockyPlanet) else "giant_planet"
        nodes.append(
            TopologyNodeV2(
                id=f"planet:{planet.id}",
                kind=kind,
                label=planet.display_name,
                description=planet.description or planet.charter.purpose,
                status=planet.status.value,
                metadata={"planet_class": planet.planet_class.value},
            )
        )

    for component in registry.components.values():
        nodes.append(
            TopologyNodeV2(
                id=f"component:{component.id}",
                kind="component",
                label=component.display_name,
                description=component.description,
                status=component.status.value,
                metadata={"component_kind": component.component_kind.value},
            )
        )

    for satellite in registry.satellites.values():
        nodes.append(
            TopologyNodeV2(
                id=f"satellite:{satellite.id}",
                kind="satellite",
                label=satellite.display_name,
                description=satellite.description,
                status=satellite.status.value,
                metadata={
                    "tool_id": satellite.tool_id,
                    "approval_required": satellite.approval_required,
                    "network_required": satellite.network_required,
                },
            )
        )

    for rogue_star in registry.rogue_stars.values():
        nodes.append(
            TopologyNodeV2(
                id=f"rogue_star:{rogue_star.id}",
                kind="rogue_star",
                label=rogue_star.display_name,
                description=rogue_star.description,
                status="external",
                metadata={"resource_kind": rogue_star.resource_kind.value},
            )
        )

    for constellation in registry.constellations.values():
        nodes.append(
            TopologyNodeV2(
                id=f"constellation:{constellation.id}",
                kind="constellation",
                label=constellation.display_name,
                description=constellation.description,
                status="active",
            )
        )
        for circle_id in constellation.circle_ids:
            orbits.append(
                TopologyOrbitV2(
                    id=f"spans:constellation:{constellation.id}->circle:{circle_id}",
                    source=f"constellation:{constellation.id}",
                    target=f"circle:{circle_id}",
                    kind="spans",
                    label="spans Circle",
                )
            )
        for orbit in constellation.orbits:
            orbits.append(
                TopologyOrbitV2(
                    id=f"constellation:{constellation.id}:{orbit.id}",
                    source=_topology_id(orbit.source.kind, orbit.source.id),
                    target=_topology_id(orbit.target.kind, orbit.target.id),
                    kind=orbit.kind.value,
                    label=orbit.label,
                )
            )

    nodes.sort(key=lambda item: item.id)
    orbits.sort(key=lambda item: item.id)
    counts = Counter(item.kind for item in nodes)
    return GalaxyTopologyV2(nodes=tuple(nodes), orbits=tuple(orbits), counts=dict(counts))


def _topology_id(kind: EntityKind, identifier: str) -> str:
    """Maps a typed reference to its public topology identifier."""

    if kind is EntityKind.PLANET:
        return f"planet:{identifier}"
    if kind is EntityKind.SATELLITE:
        return f"satellite:{identifier}"
    if kind is EntityKind.COMPONENT:
        return f"component:{identifier}"
    if kind is EntityKind.ROGUE_STAR:
        return f"rogue_star:{identifier}"
    if kind is EntityKind.CIRCLE:
        return f"circle:{identifier}"
    if kind is EntityKind.GALAXY:
        return f"galaxy:{identifier}"
    if kind is EntityKind.CONSTELLATION:
        return f"constellation:{identifier}"
    raise ValueError(f"Unsupported topology entity kind: {kind.value}")
