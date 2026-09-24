"""Created: 2026-09-24

Purpose: Executes Rocky and Giant Planets through one reusable runtime facade.
"""

from __future__ import annotations

from collections.abc import Callable

from easy_agents.galaxy.enums import MissionStatus
from easy_agents.galaxy.missions import (
    GalaxyMissionResult,
    Mission,
    PermissionGrant,
    PlanetRunResult,
    WorkOrder,
)
from easy_agents.galaxy.planets import Planet
from easy_agents.galaxy.registry import GalaxyRegistry
from easy_agents.galaxy.routing import Wormhole


PlanetHandler = Callable[[WorkOrder], str | PlanetRunResult]
"""Application callback that performs one Planet's bounded Work Order."""


class PlanetRunner:
    """Executes either Planet subclass through the same handler contract.

    The runner owns no routing policy and grants no permissions. It verifies the
    Work Order against the selected Planet's Charter, then invokes an explicitly
    registered application handler. This keeps domain models reusable without
    embedding LLM, graph, or infrastructure choices in subclasses.
    """

    def __init__(self, registry: GalaxyRegistry) -> None:
        """Initializes an empty handler registry for canonical Planets."""

        self.registry = registry
        self._handlers: dict[str, PlanetHandler] = {}

    def register(self, planet_id: str, handler: PlanetHandler) -> None:
        """Registers an application handler for one known Planet.

        Args:
            planet_id: Canonical Planet identifier.
            handler: Callable that accepts one validated Work Order.

        Raises:
            KeyError: If the Planet is not registered in the Galaxy.
            ValueError: If a handler is already registered for the Planet.
        """

        self.registry.get_planet(planet_id)
        if planet_id in self._handlers:
            raise ValueError(f"Planet {planet_id!r} already has a handler.")
        self._handlers[planet_id] = handler

    def run(self, work_order: WorkOrder) -> PlanetRunResult:
        """Validates and executes one bounded Planet Work Order."""

        planet = self.registry.get_planet(work_order.planet_id)
        self._validate_grant(planet, work_order.permission_grant)
        try:
            handler = self._handlers[planet.id]
        except KeyError as exc:
            raise KeyError(
                f"Planet {planet.id!r} has no registered execution handler."
            ) from exc
        result = handler(work_order)
        if isinstance(result, PlanetRunResult):
            if result.work_order_id != work_order.id or result.planet_id != planet.id:
                raise ValueError("Planet handler returned a result for another Work Order.")
            return result
        return PlanetRunResult(
            mission_id=work_order.mission_id,
            work_order_id=work_order.id,
            planet_id=planet.id,
            status=MissionStatus.COMPLETED,
            response=str(result),
        )

    @staticmethod
    def _validate_grant(planet: Planet, grant: PermissionGrant) -> None:
        """Rejects a Work Order that exceeds its Planet's Charter."""

        if not set(grant.effects) <= set(planet.charter.allowed_effects):
            raise ValueError(f"Work Order exceeds Planet {planet.id!r} effects.")
        if not set(grant.vault_ids) <= set(planet.charter.vault_ids):
            raise ValueError(f"Work Order exceeds Planet {planet.id!r} Vault access.")
        if not set(grant.satellite_ids) <= set(planet.charter.satellite_ids):
            raise ValueError(f"Work Order exceeds Planet {planet.id!r} Satellite access.")


class GalaxyRuntime:
    """Routes a Mission and executes its selected Planets as one bounded unit.

    This small runtime is intended for custom Galaxies and examples. Existing
    v1 applications continue through ``FleetRuntime`` until they migrate via
    the compatibility adapter.
    """

    def __init__(
        self,
        registry: GalaxyRegistry,
        *,
        wormhole: Wormhole | None = None,
        runner: PlanetRunner | None = None,
    ) -> None:
        """Composes routing and execution services over one registry."""

        self.registry = registry
        self.wormhole = wormhole or Wormhole(registry)
        self.runner = runner or PlanetRunner(registry)

    def run(self, mission: Mission) -> GalaxyMissionResult:
        """Routes and executes a Mission within its declared budget."""

        trajectory = self.wormhole.route(mission)
        results: list[PlanetRunResult] = []
        for planet_id in trajectory.planet_ids:
            planet = self.registry.get_planet(planet_id)
            grant = PermissionGrant(
                effects=tuple(
                    item
                    for item in mission.requested_effects
                    if item in planet.charter.allowed_effects
                ),
                vault_ids=tuple(
                    item
                    for item in mission.requested_vault_ids
                    if item in planet.charter.vault_ids
                ),
                satellite_ids=planet.charter.satellite_ids,
                rogue_star_ids=planet.charter.model_ids,
                allow_network=(
                    mission.allow_network and planet.charter.network_access == "allow"
                ),
            )
            work_order = WorkOrder(
                mission_id=mission.id,
                planet_id=planet.id,
                objective=mission.objective,
                permission_grant=grant,
                correlation_id=mission.id,
            )
            results.append(self.runner.run(work_order))
        statuses = {item.status for item in results}
        status = (
            MissionStatus.COMPLETED
            if statuses == {MissionStatus.COMPLETED}
            else MissionStatus.FAILED
            if MissionStatus.FAILED in statuses
            else MissionStatus.BLOCKED
        )
        return GalaxyMissionResult(
            mission_id=mission.id,
            status=status,
            trajectory=trajectory,
            results=tuple(results),
            synthesis="\n\n".join(item.response for item in results),
        )
