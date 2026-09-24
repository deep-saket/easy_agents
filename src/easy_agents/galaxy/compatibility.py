"""Created: 2026-09-24

Purpose: Adapts working version-1 fleet data into canonical Galaxy contracts.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from easy_agents.galaxy.charters import Charter
from easy_agents.galaxy.circles import Circle
from easy_agents.galaxy.constellations import Constellation, Orbit
from easy_agents.galaxy.enums import (
    ComponentKind,
    EntityKind,
    LifecycleStatus,
    OrbitKind,
    ResourceKind,
)
from easy_agents.galaxy.galaxies import Galaxy
from easy_agents.galaxy.identity import EntityRef
from easy_agents.galaxy.members import Component
from easy_agents.galaxy.operations import Gate, Vault
from easy_agents.galaxy.planets import RockyPlanet
from easy_agents.galaxy.registry import GalaxyRegistry
from easy_agents.galaxy.rogue_stars import AccessOrbit, RogueStar
from easy_agents.galaxy.satellites import Satellite

if TYPE_CHECKING:
    from easy_agents.fleet.registry import FleetRegistry


def registry_from_fleet(fleet: "FleetRegistry") -> GalaxyRegistry:
    """Converts the working v1 FleetRegistry into canonical domain objects.

    The adapter preserves all existing technical identifiers in ``legacy_ids``
    and performs no persistence mutation. It is the supported bridge for v2
    APIs while the YAML catalogs remain version 1.

    Args:
        fleet: Validated v1 registry compiled from the current catalogs.

    Returns:
        A fully validated canonical GalaxyRegistry containing all 70 current
        roles as Rocky Planets, all reusable Components and Satellites, and Mac
        Gemma as an external Rogue Star.
    """

    circle_nodes = sorted(
        (item for item in fleet.graph.nodes if item.kind == "guild"),
        key=lambda item: item.id,
    )
    circle_ids = tuple(item.id.removeprefix("guild:") for item in circle_nodes)
    fallback_circle = "commons" if "commons" in circle_ids else circle_ids[0]

    usage = _component_circle_usage(fleet)
    planets = tuple(_planet_from_manifest(fleet, item) for item in fleet.list_specialists())

    components: list[Component] = []
    satellites: list[Satellite] = []
    rogue_stars: list[RogueStar] = []
    for node in sorted(fleet.graph.nodes, key=lambda item: item.id):
        prefix, _, identifier = node.id.partition(":")
        if prefix == "tool":
            member_circles = tuple(sorted(usage["tool"].get(identifier, {fallback_circle})))
            satellites.append(
                Satellite(
                    id=identifier,
                    display_name=node.label,
                    description=node.description,
                    circle_ids=member_circles,
                    status=_status(node.status),
                    tags=tuple(node.tags),
                    legacy_ids=(node.id,),
                    tool_id=identifier,
                    effects=_tool_effects(identifier),
                    network_required=identifier in {"gmail_fetch", "email_send", "notification"},
                    approval_required=identifier in {"email_send", "notification"},
                    idempotent=identifier not in {"email_send", "notification", "memory_write"},
                    max_attempts=1,
                )
            )
        elif node.kind == "rogue_star":
            endpoint = str(node.metadata.get("endpoint", "http://127.0.0.1:8080"))
            rogue_stars.append(
                RogueStar(
                    id=identifier,
                    display_name=node.label,
                    description=node.description,
                    resource_kind=ResourceKind(
                        str(node.metadata.get("resource_kind", "service"))
                    ),
                    endpoint=endpoint,
                    model_name="gemma-4-E4B" if identifier == "mac_gemma" else None,
                    tags=tuple(node.tags),
                    legacy_ids=(node.id,),
                )
            )
        elif prefix == "capability":
            components.append(
                _component_from_node(
                    node,
                    identifier=identifier,
                    kind=ComponentKind.CAPABILITY,
                    circles=usage["capability"].get(identifier, {fallback_circle}),
                    capability_ids=(identifier,),
                )
            )
        elif prefix == "memory":
            spec = fleet.memory_scopes.get(identifier)
            components.append(
                Vault(
                    id=identifier,
                    display_name=node.label,
                    description=node.description,
                    circle_ids=tuple(
                        sorted(usage["memory"].get(identifier, {fallback_circle}))
                    ),
                    status=_status(node.status),
                    tags=tuple(node.tags),
                    legacy_ids=(node.id,),
                    sensitivity=spec.sensitivity if spec else "private",
                    writable=spec.writable if spec else True,
                    retention=spec.retention if spec else "user-controlled",
                )
            )
        elif prefix == "playbook":
            components.append(
                _component_from_node(
                    node,
                    identifier=identifier,
                    kind=ComponentKind.PLAYBOOK,
                    circles=usage["playbook"].get(identifier, {fallback_circle}),
                )
            )
        elif prefix == "policy":
            profile = fleet.policies.get(identifier)
            components.append(
                Gate(
                    id=identifier,
                    display_name=node.label,
                    description=node.description,
                    circle_ids=tuple(
                        sorted(usage["policy"].get(identifier, {fallback_circle}))
                    ),
                    status=_status(node.status),
                    tags=tuple(node.tags),
                    legacy_ids=(node.id,),
                    allowed_effects=tuple(profile.allowed_effects) if profile else ("read",),
                    approval_effects=tuple(profile.approval_effects) if profile else (),
                    denied_effects=tuple(profile.denied_effects) if profile else (),
                    external_network=profile.external_network if profile else "deny",
                )
            )
        elif prefix == "model":
            components.append(
                _component_from_node(
                    node,
                    identifier=identifier,
                    kind=ComponentKind.MODEL,
                    circles=usage["model"].get(identifier, {fallback_circle}),
                )
            )
        elif prefix == "service" and identifier != "wormhole":
            components.append(
                _component_from_node(
                    node,
                    identifier=identifier,
                    kind=ComponentKind.SERVICE,
                    circles={fallback_circle},
                )
            )

    # Custom v1 directories may compile reusable runtime defaults into their
    # Charters without projecting those packaged dependencies into the graph.
    # The compatibility boundary must adapt the validated Charter, not only its
    # visualization, so synthesize conservative canonical records for anything
    # the graph omitted.
    known_satellites = {item.id for item in satellites}
    for identifier in sorted(
        {
            item
            for manifest in fleet.specialists.values()
            for item in manifest.tool_ids
        }
        - known_satellites
    ):
        satellites.append(
            Satellite(
                id=identifier,
                display_name=_display_name(identifier),
                description="Packaged v1 tool dependency adapted as a Satellite.",
                circle_ids=tuple(
                    sorted(usage["tool"].get(identifier, {fallback_circle}))
                ),
                status=LifecycleStatus.ACTIVE,
                legacy_ids=(f"tool:{identifier}",),
                tool_id=identifier,
                effects=_tool_effects(identifier),
                network_required=identifier
                in {"gmail_fetch", "email_send", "notification"},
                approval_required=identifier in {"email_send", "notification"},
                idempotent=identifier
                not in {"email_send", "notification", "memory_write"},
                max_attempts=1,
            )
        )

    _add_missing_components(
        fleet=fleet,
        components=components,
        rogue_stars=rogue_stars,
        usage=usage,
        fallback_circle=fallback_circle,
    )

    members_by_circle: dict[str, list[EntityRef]] = defaultdict(list)
    for planet in planets:
        for circle_id in planet.circle_ids:
            members_by_circle[circle_id].append(
                EntityRef(
                    kind=EntityKind.PLANET,
                    id=planet.id,
                    legacy_id=f"specialist:{planet.id}",
                )
            )
    for component in components:
        for circle_id in component.circle_ids:
            members_by_circle[circle_id].append(
                EntityRef(
                    kind=EntityKind.COMPONENT,
                    id=component.id,
                    legacy_id=component.legacy_ids[0] if component.legacy_ids else None,
                )
            )
    for satellite in satellites:
        for circle_id in satellite.circle_ids:
            members_by_circle[circle_id].append(
                EntityRef(
                    kind=EntityKind.SATELLITE,
                    id=satellite.id,
                    legacy_id=f"tool:{satellite.id}",
                )
            )

    circles = tuple(
        Circle(
            id=node.id.removeprefix("guild:"),
            display_name=node.label,
            purpose=node.description or f"Coordinates {node.label} responsibilities.",
            members=tuple(
                sorted(
                    members_by_circle[node.id.removeprefix("guild:")],
                    key=lambda item: (item.kind.value, item.id),
                )
            ),
            tags=tuple(node.tags),
            legacy_ids=(node.id,),
        )
        for node in circle_nodes
    )

    external_access = tuple(
        AccessOrbit(
            galaxy_id="personal",
            rogue_star_id=item.id,
            allowed_effects=("inference",),
            allowed_hosts=((urlparse(str(item.endpoint)).hostname or "127.0.0.1"),),
            allow_network=False,
        )
        for item in rogue_stars
    )
    galaxy = Galaxy(
        id="personal",
        display_name="Personal Agent Galaxy",
        description="Personal, employment, scientific, and venture agent system.",
        circle_ids=circle_ids,
        external_access=external_access,
        tags=("personal", "local-first"),
        default=True,
    )
    constellation = _default_constellation(
        circles=circles,
    )
    return GalaxyRegistry(
        galaxies=(galaxy,),
        circles=circles,
        planets=planets,
        components=tuple(components),
        satellites=tuple(satellites),
        rogue_stars=tuple(rogue_stars),
        constellations=(constellation,),
    )


def _planet_from_manifest(fleet: "FleetRegistry", manifest: object) -> RockyPlanet:
    """Converts one SpecialistManifest into a Rocky Planet."""

    allowed_effects = sorted(
        {
            effect
            for policy_id in manifest.policy_ids
            for effect in fleet.policies[policy_id].allowed_effects
        }
    )
    return RockyPlanet(
        id=manifest.id,
        display_name=manifest.display_name,
        description=manifest.purpose,
        circle_ids=tuple(manifest.guilds),
        status=_status(manifest.status.value),
        tags=tuple(manifest.tags),
        legacy_ids=(f"specialist:{manifest.id}",),
        charter=Charter(
            purpose=manifest.purpose,
            capability_ids=tuple(manifest.capability_ids),
            satellite_ids=tuple(manifest.tool_ids),
            vault_ids=tuple(manifest.memory_scope_ids),
            playbook_ids=tuple(manifest.playbook_ids),
            gate_ids=tuple(manifest.policy_ids),
            model_ids=tuple(manifest.model_ids),
            allowed_effects=tuple(allowed_effects or ["read"]),
            network_access=_network_access(fleet, manifest.policy_ids),
        ),
        expertise=tuple(manifest.tags or (manifest.id.replace("_", " "),)),
        specialization_boundary=manifest.purpose,
    )


def _component_circle_usage(fleet: "FleetRegistry") -> dict[str, dict[str, set[str]]]:
    """Indexes the Circles that currently reference each reusable dependency."""

    usage: dict[str, dict[str, set[str]]] = {
        key: defaultdict(set)
        for key in ("capability", "tool", "memory", "playbook", "policy", "model")
    }
    for manifest in fleet.specialists.values():
        for kind, values in (
            ("capability", manifest.capability_ids),
            ("tool", manifest.tool_ids),
            ("memory", manifest.memory_scope_ids),
            ("playbook", manifest.playbook_ids),
            ("policy", manifest.policy_ids),
            ("model", manifest.model_ids),
        ):
            for identifier in values:
                usage[kind][identifier].update(manifest.guilds)
    return usage


def _component_from_node(
    node: object,
    *,
    identifier: str,
    kind: ComponentKind,
    circles: set[str],
    capability_ids: tuple[str, ...] = (),
) -> Component:
    """Converts one legacy graph node into a generic Component."""

    return Component(
        id=identifier,
        display_name=node.label,
        description=node.description,
        circle_ids=tuple(sorted(circles)),
        status=_status(node.status),
        tags=tuple(node.tags),
        legacy_ids=(node.id,),
        component_kind=kind,
        capability_ids=capability_ids,
    )


def _add_missing_components(
    *,
    fleet: "FleetRegistry",
    components: list[Component],
    rogue_stars: list[RogueStar],
    usage: dict[str, dict[str, set[str]]],
    fallback_circle: str,
) -> None:
    """Adapts Charter dependencies omitted from a custom v1 graph projection."""

    known = {item.id for item in components}
    external = {item.id for item in rogue_stars}
    requirements = {
        "capability": (
            ComponentKind.CAPABILITY,
            {item for manifest in fleet.specialists.values() for item in manifest.capability_ids},
        ),
        "memory": (
            ComponentKind.VAULT,
            {item for manifest in fleet.specialists.values() for item in manifest.memory_scope_ids},
        ),
        "playbook": (
            ComponentKind.PLAYBOOK,
            {item for manifest in fleet.specialists.values() for item in manifest.playbook_ids},
        ),
        "policy": (
            ComponentKind.GATE,
            {item for manifest in fleet.specialists.values() for item in manifest.policy_ids},
        ),
        "model": (
            ComponentKind.MODEL,
            {item for manifest in fleet.specialists.values() for item in manifest.model_ids},
        ),
    }
    for legacy_kind, (component_kind, identifiers) in requirements.items():
        for identifier in sorted(identifiers - known - external):
            circles = tuple(
                sorted(usage[legacy_kind].get(identifier, {fallback_circle}))
            )
            common = {
                "id": identifier,
                "display_name": _display_name(identifier),
                "description": (
                    f"Packaged v1 {legacy_kind} dependency adapted as a Component."
                ),
                "circle_ids": circles,
                "status": LifecycleStatus.ACTIVE,
                "legacy_ids": (f"{legacy_kind}:{identifier}",),
            }
            if component_kind is ComponentKind.VAULT:
                spec = fleet.memory_scopes.get(identifier)
                components.append(
                    Vault(
                        **common,
                        sensitivity=spec.sensitivity if spec else "private",
                        writable=spec.writable if spec else True,
                        retention=spec.retention if spec else "user-controlled",
                    )
                )
            elif component_kind is ComponentKind.GATE:
                profile = fleet.policies.get(identifier)
                components.append(
                    Gate(
                        **common,
                        allowed_effects=(
                            tuple(profile.allowed_effects) if profile else ("read",)
                        ),
                        approval_effects=(
                            tuple(profile.approval_effects) if profile else ()
                        ),
                        denied_effects=(
                            tuple(profile.denied_effects) if profile else ()
                        ),
                        external_network=(
                            profile.external_network if profile else "deny"
                        ),
                    )
                )
            else:
                components.append(
                    Component(
                        **common,
                        component_kind=component_kind,
                        capability_ids=(identifier,)
                        if component_kind is ComponentKind.CAPABILITY
                        else (),
                    )
                )
            known.add(identifier)


def _display_name(identifier: str) -> str:
    """Creates a readable compatibility label without changing the stable ID."""

    return identifier.replace("_", " ").replace(".", " ").title()


def _default_constellation(
    *,
    circles: tuple[Circle, ...],
) -> Constellation:
    """Builds one connected compatibility overlay from canonical references."""

    nodes: list[EntityRef] = []
    orbits: list[Orbit] = []
    previous_circle_ref: EntityRef | None = None
    for circle in circles:
        circle_ref = EntityRef(kind=EntityKind.CIRCLE, id=circle.id)
        nodes.append(circle_ref)
        if previous_circle_ref is not None:
            orbits.append(
                Orbit(
                    id=f"orbit-{len(orbits) + 1}",
                    source=previous_circle_ref,
                    target=circle_ref,
                    kind=OrbitKind.CONNECTS,
                    label="overlaps operationally",
                )
            )
        previous_circle_ref = circle_ref
        for member in circle.members:
            if member not in nodes:
                nodes.append(member)
            orbits.append(
                Orbit(
                    id=f"orbit-{len(orbits) + 1}",
                    source=circle_ref,
                    target=member,
                    kind=OrbitKind.MEMBER_OF,
                    label="contains Circle Member",
                )
            )
        # Components shared by many Circles intentionally create overlapping
        # neighborhoods, so duplicate member Orbits across Circles are valid.
    return Constellation(
        id="personal_operations",
        display_name="Personal Operations Constellation",
        description="Connected compatibility overlay spanning the Personal Agent Galaxy.",
        circle_ids=tuple(item.id for item in circles),
        nodes=tuple(nodes),
        orbits=tuple(orbits),
        tags=("compatibility", "personal", "connected"),
    )


def _status(value: str) -> LifecycleStatus:
    """Maps v1 lifecycle and implementation labels to canonical status."""

    normalized = value.lower()
    if normalized in {"implemented", "live", "available"}:
        return LifecycleStatus.ACTIVE
    if normalized == "planned":
        return LifecycleStatus.PROPOSED
    try:
        return LifecycleStatus(normalized)
    except ValueError:
        return LifecycleStatus.PROPOSED


def _tool_effects(identifier: str) -> tuple[str, ...]:
    """Returns conservative compatibility effects for packaged Satellites."""

    if identifier in {"email_send", "notification"}:
        return ("external_send",)
    if identifier in {"memory_write", "draft_reply", "email_classifier"}:
        return ("write",)
    if identifier in {"calculate", "unit_convert"}:
        return ("compute",)
    return ("read",)


def _network_access(fleet: "FleetRegistry", policy_ids: list[str]) -> str:
    """Returns the most permissive network mode declared by v1 policies."""

    values = {fleet.policies[item].external_network for item in policy_ids}
    if "allow" in values:
        return "allow"
    if "approval" in values:
        return "approval"
    return "deny"
