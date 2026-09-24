"""Created: 2026-09-24

Purpose: Represents computed one-Planet graph neighborhoods.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from easy_agents.galaxy.constellations import Orbit
from easy_agents.galaxy.identity import EntityRef, PlanetId


class SolarSystem(BaseModel):
    """Contains a Planet and every entity directly connected to it.

    Solar Systems are projections, not persisted workers or ownership
    boundaries. Two Solar Systems may overlap when their Planets share a
    Satellite, Vault, Playbook, Gate, model, or service.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    center_planet_id: PlanetId
    neighbors: tuple[EntityRef, ...]
    orbits: tuple[Orbit, ...]

    @model_validator(mode="after")
    def validate_neighborhood(self) -> "SolarSystem":
        """Ensures every included Orbit touches the center Planet."""

        invalid = [
            orbit.id
            for orbit in self.orbits
            if not (
                (orbit.source.id == self.center_planet_id and orbit.source.kind.value == "planet")
                or (orbit.target.id == self.center_planet_id and orbit.target.kind.value == "planet")
            )
        ]
        if invalid:
            raise ValueError(
                "Solar System contains Orbits outside the center neighborhood: "
                + ", ".join(invalid)
            )
        keys = [(item.kind, item.id) for item in self.neighbors]
        if len(keys) != len(set(keys)):
            raise ValueError("Solar System contains duplicate neighbors.")
        return self
