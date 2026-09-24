"""Created: 2026-09-24

Purpose: Simplifies assembling immutable Galaxy entities into a validated registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from easy_agents.galaxy.circles import Circle
from easy_agents.galaxy.constellations import Constellation
from easy_agents.galaxy.enums import EntityKind
from easy_agents.galaxy.galaxies import Galaxy
from easy_agents.galaxy.identity import EntityRef
from easy_agents.galaxy.members import Component
from easy_agents.galaxy.planets import Planet
from easy_agents.galaxy.registry import GalaxyRegistry
from easy_agents.galaxy.rogue_stars import RogueStar
from easy_agents.galaxy.satellites import Satellite


@dataclass(slots=True)
class GalaxyBuilder:
    """Collects domain objects and derives symmetric Circle membership.

    The builder is a convenience for configuration code. It remains deliberately
    small: it does not invent identifiers, permissions, Charters, or ownership.
    ``build()`` creates new Circle copies containing references derived from each
    member's ``circle_ids`` and then delegates all invariants to GalaxyRegistry.
    """

    _galaxies: dict[str, Galaxy] = field(default_factory=dict)
    _circles: dict[str, Circle] = field(default_factory=dict)
    _planets: dict[str, Planet] = field(default_factory=dict)
    _components: dict[str, Component] = field(default_factory=dict)
    _satellites: dict[str, Satellite] = field(default_factory=dict)
    _rogue_stars: dict[str, RogueStar] = field(default_factory=dict)
    _constellations: dict[str, Constellation] = field(default_factory=dict)

    def add(self, entity: object) -> "GalaxyBuilder":
        """Adds one supported domain entity and returns this builder.

        Args:
            entity: Galaxy, Circle, Planet, Component, Satellite, Rogue Star, or
                Constellation instance.

        Returns:
            This builder, enabling fluent chained calls.

        Raises:
            TypeError: If the entity type is unsupported.
            ValueError: If the same kind and identifier were already added.
        """

        if isinstance(entity, Galaxy):
            target, label = self._galaxies, "Galaxy"
        elif isinstance(entity, Circle):
            target, label = self._circles, "Circle"
        elif isinstance(entity, Planet):
            target, label = self._planets, "Planet"
        elif isinstance(entity, Satellite):
            target, label = self._satellites, "Satellite"
        elif isinstance(entity, Component):
            target, label = self._components, "Component"
        elif isinstance(entity, RogueStar):
            target, label = self._rogue_stars, "Rogue Star"
        elif isinstance(entity, Constellation):
            target, label = self._constellations, "Constellation"
        else:
            raise TypeError(f"Unsupported Galaxy entity: {type(entity).__name__}")
        identifier = str(entity.id)
        if identifier in target:
            raise ValueError(f"Duplicate {label} identifier: {identifier}")
        target[identifier] = entity
        return self

    def build(self) -> GalaxyRegistry:
        """Derives Circle member references and returns a validated registry."""

        member_refs: dict[str, dict[tuple[EntityKind, str], EntityRef]] = {
            identifier: {
                (item.kind, item.id): item
                for item in circle.members
            }
            for identifier, circle in self._circles.items()
        }
        for kind, values in (
            (EntityKind.PLANET, self._planets.values()),
            (EntityKind.COMPONENT, self._components.values()),
            (EntityKind.SATELLITE, self._satellites.values()),
        ):
            for member in values:
                for circle_id in member.circle_ids:
                    if circle_id not in member_refs:
                        raise ValueError(
                            f"{kind.value.title()} {member.id!r} references unknown "
                            f"Circle {circle_id!r}."
                        )
                    reference = EntityRef(
                        kind=kind,
                        id=member.id,
                        legacy_id=member.legacy_ids[0] if member.legacy_ids else None,
                    )
                    member_refs[circle_id][(kind, member.id)] = reference

        circles = tuple(
            circle.model_copy(
                update={
                    "members": tuple(
                        member_refs[circle.id][key]
                        for key in sorted(
                            member_refs[circle.id],
                            key=lambda item: (item[0].value, item[1]),
                        )
                    )
                }
            )
            for circle in self._circles.values()
        )
        return GalaxyRegistry(
            galaxies=self._galaxies.values(),
            circles=circles,
            planets=self._planets.values(),
            components=self._components.values(),
            satellites=self._satellites.values(),
            rogue_stars=self._rogue_stars.values(),
            constellations=self._constellations.values(),
        )
