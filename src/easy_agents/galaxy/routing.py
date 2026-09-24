"""Created: 2026-09-24

Purpose: Implements canonical Portal and Wormhole routing contracts.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from easy_agents.galaxy.circles import Circle
from easy_agents.galaxy.enums import LifecycleStatus
from easy_agents.galaxy.galaxies import Galaxy
from easy_agents.galaxy.missions import Mission, Trajectory
from easy_agents.galaxy.planets import Planet
from easy_agents.galaxy.registry import GalaxyRegistry


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "i",
    "in",
    "is",
    "me",
    "my",
    "of",
    "on",
    "please",
    "the",
    "to",
    "with",
}


class PortalRequest(BaseModel):
    """Wraps a Mission with the human-facing channel that captured it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    portal_id: str = Field(min_length=1, max_length=128)
    mission: Mission
    principal_id: str | None = Field(default=None, max_length=256)


@runtime_checkable
class Portal(Protocol):
    """Protocol implemented by chat, voice, CLI, HTTP, or other entrypoints."""

    def receive(self) -> PortalRequest:
        """Returns one validated request captured by the Portal."""


class Wormhole:
    """Routes Missions directly through Galaxy and Circle to Planets.

    The implementation is deterministic and model-free. It grants no authority;
    it only selects an explainable path from already registered entities.
    Runtime policy produces Permission Grants after routing.
    """

    def __init__(self, registry: GalaxyRegistry, *, wormhole_id: str = "wormhole") -> None:
        """Initializes a router over one validated registry.

        Args:
            registry: Source of Galaxies, Circles, and eligible Planets.
            wormhole_id: Stable identifier included in every Trajectory.
        """

        self.registry = registry
        self.wormhole_id = wormhole_id

    def route(self, mission: Mission) -> Trajectory:
        """Returns an explainable canonical Trajectory for a Mission.

        Args:
            mission: Validated user goal and bounded routing preferences.

        Returns:
            A direct Wormhole → Galaxy → Circle → Planet route.

        Raises:
            ValueError: If no routable Planet exists in the selected Galaxy or
                a preferred entity conflicts with ownership/membership.
        """

        galaxy = self._select_galaxy(mission)
        circles = [self.registry.circles[item] for item in galaxy.circle_ids]
        if mission.preferred_circle_id:
            if mission.preferred_circle_id not in galaxy.circle_ids:
                raise ValueError(
                    f"Preferred Circle {mission.preferred_circle_id!r} is not in "
                    f"Galaxy {galaxy.id!r}."
                )
            selected_circles = [self.registry.get_circle(mission.preferred_circle_id)]
        else:
            selected_circles = self._rank_circles(mission.objective, circles)

        if mission.preferred_planet_id:
            planet = self.registry.get_planet(mission.preferred_planet_id)
            if not set(planet.circle_ids) & {item.id for item in selected_circles}:
                raise ValueError(
                    f"Preferred Planet {planet.id!r} is not a member of the selected Circle."
                )
            selected_planets = [planet]
        else:
            selected_planets = self._rank_planets(
                mission.objective,
                selected_circles,
                limit=mission.team_size,
            )
        if not selected_planets:
            raise ValueError(f"Galaxy {galaxy.id!r} has no routable Planet for this Mission.")

        selected_circle_ids: list[str] = []
        for planet in selected_planets:
            circle_id = next(
                item.id for item in selected_circles if item.id in planet.circle_ids
            )
            if circle_id not in selected_circle_ids:
                selected_circle_ids.append(circle_id)
        query = _tokens(mission.objective)
        matched = sorted(
            query
            & {
                token
                for item in (*selected_circles, *selected_planets)
                for token in _entity_tokens(item)
            }
        )
        return Trajectory(
            mission_id=mission.id,
            wormhole_id=self.wormhole_id,
            galaxy_id=galaxy.id,
            circle_ids=tuple(selected_circle_ids),
            planet_ids=tuple(item.id for item in selected_planets),
            matched_terms=tuple(matched),
        )

    def _select_galaxy(self, mission: Mission) -> Galaxy:
        """Selects an explicit, default, or sole Galaxy deterministically."""

        if mission.galaxy_id:
            return self.registry.get_galaxy(mission.galaxy_id)
        defaults = [item for item in self.registry.galaxies.values() if item.default]
        if len(defaults) == 1:
            return defaults[0]
        if len(self.registry.galaxies) == 1:
            return next(iter(self.registry.galaxies.values()))
        if not defaults:
            raise ValueError("Mission must select a Galaxy when no default is configured.")
        raise ValueError("Mission must select a Galaxy because multiple defaults exist.")

    @staticmethod
    def _rank_circles(objective: str, circles: list[Circle]) -> list[Circle]:
        """Ranks Circles by deterministic token overlap and returns the best."""

        query = _tokens(objective)
        ranked = sorted(
            circles,
            key=lambda item: (
                -len(query & _entity_tokens(item)),
                str(getattr(item, "display_name")).lower(),
                str(getattr(item, "id")),
            ),
        )
        return ranked[:1]

    def _rank_planets(
        self,
        objective: str,
        circles: list[Circle],
        *,
        limit: int,
    ) -> list[Planet]:
        """Ranks eligible Planets within selected Circles."""

        circle_ids = {item.id for item in circles}
        query = _tokens(objective)
        eligible = [
            planet
            for planet in self.registry.planets.values()
            if circle_ids.intersection(planet.circle_ids)
            and planet.status not in {LifecycleStatus.QUARANTINED, LifecycleStatus.RETIRED}
        ]
        eligible.sort(
            key=lambda planet: (
                -len(query & _planet_tokens(planet)),
                planet.status is not LifecycleStatus.ACTIVE,
                planet.display_name.lower(),
                planet.id,
            )
        )
        return eligible[:limit]


def _tokens(value: str) -> set[str]:
    """Normalizes free text into routing tokens."""

    return {
        token
        for token in _TOKEN_RE.findall(value.lower())
        if token not in _STOP_WORDS and len(token) > 1
    }


def _entity_tokens(entity: object) -> set[str]:
    """Builds searchable tokens from a Circle or Planet-like object."""

    values = [
        str(getattr(entity, "id", "")).replace("_", " "),
        str(getattr(entity, "display_name", "")),
        str(getattr(entity, "purpose", "")),
        str(getattr(entity, "description", "")),
        " ".join(getattr(entity, "tags", ())),
    ]
    return _tokens(" ".join(values))


def _planet_tokens(planet: Planet) -> set[str]:
    """Builds searchable tokens from a Planet and its Charter."""

    return (
        _entity_tokens(planet)
        | _tokens(planet.charter.purpose)
        | _tokens(" ".join(getattr(planet, "expertise", ())))
        | _tokens(" ".join(getattr(planet, "coordination_domains", ())))
    )
