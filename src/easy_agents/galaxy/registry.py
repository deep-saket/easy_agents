"""Created: 2026-09-24

Purpose: Resolves and validates complete Galaxy domain object collections.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Iterable, Mapping

from easy_agents.galaxy.circles import Circle
from easy_agents.galaxy.constellations import Constellation, Orbit
from easy_agents.galaxy.enums import ComponentKind, EntityKind
from easy_agents.galaxy.galaxies import Galaxy
from easy_agents.galaxy.identity import EntityRef
from easy_agents.galaxy.members import Component
from easy_agents.galaxy.planets import GiantPlanet, Planet, RockyPlanet
from easy_agents.galaxy.rogue_stars import RogueStar
from easy_agents.galaxy.satellites import Satellite
from easy_agents.galaxy.solar_systems import SolarSystem


class GalaxyRegistry:
    """Validated read-only index of canonical Galaxy domain entities.

    The registry is the composition root for domain data. It validates
    ownership, membership, external access, and graph references once, then
    exposes immutable mapping views to routing, APIs, runtimes, and projections.
    It does not execute Planets or Satellites.
    """

    def __init__(
        self,
        *,
        galaxies: Iterable[Galaxy],
        circles: Iterable[Circle],
        planets: Iterable[Planet],
        components: Iterable[Component] = (),
        satellites: Iterable[Satellite] = (),
        rogue_stars: Iterable[RogueStar] = (),
        constellations: Iterable[Constellation] = (),
    ) -> None:
        """Builds and validates a canonical registry.

        Args:
            galaxies: Top-level ownership aggregates.
            circles: Domain and responsibility groups owned by Galaxies.
            planets: Rocky and Giant agent definitions.
            components: Non-Satellite Components.
            satellites: Callable tool-backed Components.
            rogue_stars: External resources owned by no Galaxy.
            constellations: Connected graph overlays referencing registered
                entities.

        Raises:
            ValueError: If identifiers collide or any relationship is invalid.
        """

        galaxy_index = _unique("Galaxy", galaxies)
        circle_index = _unique("Circle", circles)
        planet_index = _unique("Planet", planets)
        component_index = _unique("Component", components)
        satellite_index = _unique("Satellite", satellites)
        rogue_star_index = _unique("Rogue Star", rogue_stars)
        constellation_index = _unique("Constellation", constellations)

        overlap = sorted(set(component_index) & set(satellite_index))
        if overlap:
            raise ValueError(
                "Component and Satellite identifiers must be distinct: "
                + ", ".join(overlap)
            )

        invalid_planets = sorted(
            item.id
            for item in planet_index.values()
            if not isinstance(item, (RockyPlanet, GiantPlanet))
        )
        if invalid_planets:
            raise ValueError(
                "Every Planet must be a RockyPlanet or GiantPlanet: "
                + ", ".join(invalid_planets)
            )

        self._validate_ownership(
            galaxies=galaxy_index,
            circles=circle_index,
            rogue_stars=rogue_star_index,
        )
        self._validate_membership(
            circles=circle_index,
            planets=planet_index,
            components=component_index,
            satellites=satellite_index,
        )
        self._validate_charters(
            planets=planet_index,
            components=component_index,
            satellites=satellite_index,
            rogue_stars=rogue_star_index,
        )
        self._validate_constellations(
            constellations=constellation_index,
            galaxies=galaxy_index,
            circles=circle_index,
            planets=planet_index,
            components=component_index,
            satellites=satellite_index,
        )

        self.galaxies: Mapping[str, Galaxy] = MappingProxyType(galaxy_index)
        self.circles: Mapping[str, Circle] = MappingProxyType(circle_index)
        self.planets: Mapping[str, Planet] = MappingProxyType(planet_index)
        self.components: Mapping[str, Component] = MappingProxyType(component_index)
        self.satellites: Mapping[str, Satellite] = MappingProxyType(satellite_index)
        self.rogue_stars: Mapping[str, RogueStar] = MappingProxyType(rogue_star_index)
        self.constellations: Mapping[str, Constellation] = MappingProxyType(
            constellation_index
        )

    def get_galaxy(self, galaxy_id: str) -> Galaxy:
        """Returns one Galaxy or raises a descriptive ``KeyError``."""

        return _get(self.galaxies, galaxy_id, "Galaxy")

    def get_circle(self, circle_id: str) -> Circle:
        """Returns one Circle or raises a descriptive ``KeyError``."""

        return _get(self.circles, circle_id, "Circle")

    def get_planet(self, planet_id: str) -> Planet:
        """Returns one Rocky or Giant Planet."""

        return _get(self.planets, planet_id, "Planet")

    def get_component(self, component_id: str) -> Component:
        """Returns one Component, including a Satellite when applicable."""

        if component_id in self.satellites:
            return self.satellites[component_id]
        return _get(self.components, component_id, "Component")

    def resolve(self, reference: EntityRef) -> object:
        """Resolves a typed reference and verifies its declared kind."""

        index: Mapping[str, object]
        if reference.kind is EntityKind.GALAXY:
            index = self.galaxies
        elif reference.kind is EntityKind.CIRCLE:
            index = self.circles
        elif reference.kind is EntityKind.PLANET:
            index = self.planets
        elif reference.kind is EntityKind.COMPONENT:
            index = self.components
        elif reference.kind is EntityKind.SATELLITE:
            index = self.satellites
        elif reference.kind is EntityKind.CONSTELLATION:
            index = self.constellations
        elif reference.kind is EntityKind.ROGUE_STAR:
            index = self.rogue_stars
        else:
            raise KeyError(f"Wormhole reference {reference.id!r} is a service, not registry data.")
        return _get(index, reference.id, reference.kind.value)

    def circles_for_planet(self, planet_id: str) -> tuple[Circle, ...]:
        """Returns every Circle that contains the selected Planet."""

        planet = self.get_planet(planet_id)
        return tuple(self.circles[item] for item in planet.circle_ids)

    def solar_system(self, planet_id: str) -> SolarSystem:
        """Computes the direct graph neighborhood around one Planet.

        Args:
            planet_id: Canonical Planet identifier.

        Returns:
            A deterministic Solar System projection assembled from registered
            Constellation Orbits.
        """

        self.get_planet(planet_id)
        connected: list[Orbit] = []
        neighbors: dict[tuple[EntityKind, str], EntityRef] = {}
        for constellation in self.constellations.values():
            for orbit in constellation.orbits:
                if orbit.source.kind is EntityKind.PLANET and orbit.source.id == planet_id:
                    connected.append(orbit)
                    neighbors[(orbit.target.kind, orbit.target.id)] = orbit.target
                elif orbit.target.kind is EntityKind.PLANET and orbit.target.id == planet_id:
                    connected.append(orbit)
                    neighbors[(orbit.source.kind, orbit.source.id)] = orbit.source
        return SolarSystem(
            center_planet_id=planet_id,
            neighbors=tuple(
                neighbors[key]
                for key in sorted(neighbors, key=lambda item: (item[0].value, item[1]))
            ),
            orbits=tuple(sorted(connected, key=lambda item: item.id)),
        )

    def summary(self) -> dict[str, int]:
        """Returns stable entity counts for APIs, diagnostics, and tests."""

        return {
            "galaxies": len(self.galaxies),
            "circles": len(self.circles),
            "planets": len(self.planets),
            "components": len(self.components),
            "satellites": len(self.satellites),
            "rogue_stars": len(self.rogue_stars),
            "constellations": len(self.constellations),
        }

    @staticmethod
    def _validate_ownership(
        *,
        galaxies: Mapping[str, Galaxy],
        circles: Mapping[str, Circle],
        rogue_stars: Mapping[str, RogueStar],
    ) -> None:
        """Validates Galaxy ownership and external access references."""

        owned: dict[str, str] = {}
        defaults = [item.id for item in galaxies.values() if item.default]
        if len(defaults) > 1:
            raise ValueError(
                "At most one Galaxy may be the default: " + ", ".join(defaults)
            )
        for galaxy in galaxies.values():
            for circle_id in galaxy.circle_ids:
                if circle_id not in circles:
                    raise ValueError(
                        f"Galaxy {galaxy.id!r} references unknown Circle {circle_id!r}."
                    )
                previous = owned.setdefault(circle_id, galaxy.id)
                if previous != galaxy.id:
                    raise ValueError(
                        f"Circle {circle_id!r} is owned by both {previous!r} and {galaxy.id!r}."
                    )
            for access in galaxy.external_access:
                if access.rogue_star_id not in rogue_stars:
                    raise ValueError(
                        f"Galaxy {galaxy.id!r} accesses unknown Rogue Star "
                        f"{access.rogue_star_id!r}."
                    )
        unowned = sorted(set(circles) - set(owned))
        if unowned:
            raise ValueError("Every Circle must belong to one Galaxy: " + ", ".join(unowned))

    @staticmethod
    def _validate_membership(
        *,
        circles: Mapping[str, Circle],
        planets: Mapping[str, Planet],
        components: Mapping[str, Component],
        satellites: Mapping[str, Satellite],
    ) -> None:
        """Validates both sides of Circle membership references."""

        for circle in circles.values():
            for reference in circle.members:
                if reference.kind is EntityKind.PLANET:
                    member = _get(planets, reference.id, "Planet")
                elif reference.kind is EntityKind.SATELLITE:
                    member = _get(satellites, reference.id, "Satellite")
                else:
                    member = _get(components, reference.id, "Component")
                if circle.id not in member.circle_ids:
                    raise ValueError(
                        f"Circle {circle.id!r} references {reference.canonical_id}, "
                        "but the member does not declare that Circle."
                    )
        for member in (*planets.values(), *components.values(), *satellites.values()):
            for circle_id in member.circle_ids:
                circle = _get(circles, circle_id, "Circle")
                expected_kind = (
                    EntityKind.PLANET
                    if isinstance(member, Planet)
                    else EntityKind.SATELLITE
                    if isinstance(member, Satellite)
                    else EntityKind.COMPONENT
                )
                if not any(
                    item.kind is expected_kind and item.id == member.id
                    for item in circle.members
                ):
                    raise ValueError(
                        f"{expected_kind.value.title()} {member.id!r} declares Circle "
                        f"{circle_id!r}, but the Circle does not reference it."
                    )

    @staticmethod
    def _validate_constellations(
        *,
        constellations: Mapping[str, Constellation],
        galaxies: Mapping[str, Galaxy],
        circles: Mapping[str, Circle],
        planets: Mapping[str, Planet],
        components: Mapping[str, Component],
        satellites: Mapping[str, Satellite],
    ) -> None:
        """Validates graph references without converting overlays into owners."""

        known_circles = set(circles)
        owned_circles = {item for galaxy in galaxies.values() for item in galaxy.circle_ids}
        for constellation in constellations.values():
            missing_circles = sorted(set(constellation.circle_ids) - known_circles)
            if missing_circles:
                raise ValueError(
                    f"Constellation {constellation.id!r} references unknown Circles: "
                    + ", ".join(missing_circles)
                )
            if not set(constellation.circle_ids) <= owned_circles:
                raise ValueError(
                    f"Constellation {constellation.id!r} references unowned Circles."
                )
            declared_circles = set(constellation.circle_ids)
            for reference in constellation.nodes:
                indexes: dict[EntityKind, Mapping[str, object]] = {
                    EntityKind.CIRCLE: circles,
                    EntityKind.PLANET: planets,
                    EntityKind.COMPONENT: components,
                    EntityKind.SATELLITE: satellites,
                }
                if reference.kind not in indexes:
                    raise ValueError(
                        f"Constellation {constellation.id!r} cannot contain "
                        f"{reference.kind.value!r} references."
                    )
                entity = _get(
                    indexes[reference.kind], reference.id, reference.kind.value
                )
                if reference.kind is EntityKind.CIRCLE:
                    if reference.id not in declared_circles:
                        raise ValueError(
                            f"Constellation {constellation.id!r} contains Circle "
                            f"{reference.id!r} outside its declared Circles."
                        )
                elif not declared_circles.intersection(entity.circle_ids):
                    raise ValueError(
                        f"Constellation {constellation.id!r} contains "
                        f"{reference.canonical_id} outside its declared Circles."
                    )

    @staticmethod
    def _validate_charters(
        *,
        planets: Mapping[str, Planet],
        components: Mapping[str, Component],
        satellites: Mapping[str, Satellite],
        rogue_stars: Mapping[str, RogueStar],
    ) -> None:
        """Rejects missing Charter dependencies and delegation targets."""

        by_kind: dict[ComponentKind, set[str]] = {
            kind: {
                item.id
                for item in components.values()
                if item.component_kind is kind
            }
            for kind in ComponentKind
        }
        checks = (
            ("capabilities", "capability_ids", by_kind[ComponentKind.CAPABILITY]),
            ("Satellites", "satellite_ids", set(satellites)),
            ("Vaults", "vault_ids", by_kind[ComponentKind.VAULT]),
            ("Playbooks", "playbook_ids", by_kind[ComponentKind.PLAYBOOK]),
            ("Gates", "gate_ids", by_kind[ComponentKind.GATE]),
            (
                "models or Rogue Stars",
                "model_ids",
                by_kind[ComponentKind.MODEL] | set(rogue_stars),
            ),
        )
        for planet in planets.values():
            for label, field_name, known in checks:
                missing = sorted(set(getattr(planet.charter, field_name)) - known)
                if missing:
                    raise ValueError(
                        f"Planet {planet.id!r} references unknown {label}: "
                        + ", ".join(missing)
                    )
            if isinstance(planet, GiantPlanet):
                missing_targets = sorted(set(planet.delegation_targets) - set(planets))
                if missing_targets:
                    raise ValueError(
                        f"Giant Planet {planet.id!r} references unknown delegation "
                        "targets: " + ", ".join(missing_targets)
                    )


def _unique(label: str, values: Iterable[object]) -> dict[str, object]:
    """Indexes objects by ``id`` and rejects duplicate identifiers."""

    result: dict[str, object] = {}
    for value in values:
        identifier = str(getattr(value, "id"))
        if identifier in result:
            raise ValueError(f"Duplicate {label} identifier: {identifier}")
        result[identifier] = value
    return result


def _get(values: Mapping[str, object], identifier: str, label: str):
    """Returns one indexed value with a descriptive missing-reference error."""

    try:
        return values[identifier]
    except KeyError as exc:
        raise KeyError(f"Unknown {label}: {identifier}") from exc
