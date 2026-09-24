"""Created: 2026-09-24

Purpose: Defines the top-level Galaxy ownership and isolation aggregate.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easy_agents.galaxy.identity import CircleId, GalaxyId
from easy_agents.galaxy.rogue_stars import AccessOrbit


class Galaxy(BaseModel):
    """Top-level ownership and isolation boundary for an agent system.

    A Galaxy directly owns Circles. It can access—but never own—Rogue Stars
    through explicit Access Orbits. The aggregate deliberately does not embed
    mutable runtime workers; a ``GalaxyRegistry`` resolves referenced objects.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: GalaxyId
    display_name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4_000)
    circle_ids: tuple[CircleId, ...] = Field(min_length=1)
    external_access: tuple[AccessOrbit, ...] = ()
    tags: tuple[str, ...] = ()
    default: bool = False

    @model_validator(mode="after")
    def validate_ownership(self) -> "Galaxy":
        """Rejects duplicate Circles and misdirected Access Orbits."""

        if len(self.circle_ids) != len(set(self.circle_ids)):
            raise ValueError(f"Galaxy {self.id!r} contains duplicate Circles.")
        external_keys = [item.rogue_star_id for item in self.external_access]
        if len(external_keys) != len(set(external_keys)):
            raise ValueError(f"Galaxy {self.id!r} has duplicate Rogue Star access.")
        wrong_owner = [item.rogue_star_id for item in self.external_access if item.galaxy_id != self.id]
        if wrong_owner:
            raise ValueError(
                f"Galaxy {self.id!r} contains Access Orbits owned by another Galaxy."
            )
        return self
