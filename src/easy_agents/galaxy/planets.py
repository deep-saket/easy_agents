"""Created: 2026-09-24

Purpose: Implements Planet inheritance for specialist and broad agents.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from easy_agents.galaxy.charters import Charter
from easy_agents.galaxy.enums import MemberKind, PlanetClass
from easy_agents.galaxy.members import CircleMember


class Planet(CircleMember):
    """Base model for an autonomous, accountable agent inside a Circle.

    Applications normally instantiate :class:`RockyPlanet` or
    :class:`GiantPlanet`, not this base directly. Both subclasses share the
    same Charter and are executed by the same ``PlanetRunner``.
    """

    member_kind: Literal[MemberKind.PLANET] = MemberKind.PLANET
    planet_class: PlanetClass
    charter: Charter


class RockyPlanet(Planet):
    """A specialist Planet with narrow expertise and an explicit boundary.

    Use a Rocky Planet when work requires one bounded area of expertise—for
    example RF link budgets, clinical evidence, pantry planning, or tax filing.
    """

    planet_class: Literal[PlanetClass.ROCKY] = PlanetClass.ROCKY
    expertise: tuple[str, ...] = Field(min_length=1)
    specialization_boundary: str = Field(min_length=3, max_length=2_000)

    @model_validator(mode="after")
    def validate_expertise(self) -> "RockyPlanet":
        """Rejects duplicate expertise labels."""

        if len(self.expertise) != len(set(self.expertise)):
            raise ValueError(f"Rocky Planet {self.id!r} contains duplicate expertise.")
        return self


class GiantPlanet(Planet):
    """A broad Planet that coordinates varied work and bounded delegation.

    A Giant Planet is not more privileged than a Rocky Planet. It receives the
    same kind of Work Order and may delegate only within the Mission's narrowed
    grant and its explicit ``delegation_targets`` allowlist.
    """

    planet_class: Literal[PlanetClass.GIANT] = PlanetClass.GIANT
    coordination_domains: tuple[str, ...] = Field(min_length=1)
    delegation_targets: tuple[str, ...] = ()
    max_delegation_depth: int = Field(default=1, ge=0, le=8)

    @model_validator(mode="after")
    def validate_delegation_policy(self) -> "GiantPlanet":
        """Rejects duplicate coordination and delegation declarations."""

        if len(self.coordination_domains) != len(set(self.coordination_domains)):
            raise ValueError(f"Giant Planet {self.id!r} has duplicate domains.")
        if len(self.delegation_targets) != len(set(self.delegation_targets)):
            raise ValueError(f"Giant Planet {self.id!r} has duplicate delegation targets.")
        if self.id in self.delegation_targets:
            raise ValueError("A Giant Planet cannot delegate directly to itself.")
        return self
