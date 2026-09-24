"""Created: 2026-09-24

Purpose: Defines Circle aggregates and their validated member references.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easy_agents.galaxy.enums import EntityKind
from easy_agents.galaxy.identity import CircleId, EntityRef


class Circle(BaseModel):
    """Groups related Planets and Components inside a Galaxy.

    A Circle is an ownership and routing group such as Home, Energy, or Medical
    Deep-Tech. It is not an executing agent. Members may appear in more than one
    Circle, but a registry validates every reference before use.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: CircleId
    display_name: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=3, max_length=4_000)
    members: tuple[EntityRef, ...] = ()
    tags: tuple[str, ...] = ()
    legacy_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_members(self) -> "Circle":
        """Rejects duplicate and structurally invalid Circle membership."""

        keys = [(item.kind, item.id) for item in self.members]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Circle {self.id!r} contains duplicate members.")
        allowed = {EntityKind.PLANET, EntityKind.COMPONENT, EntityKind.SATELLITE}
        invalid = sorted(item.canonical_id for item in self.members if item.kind not in allowed)
        if invalid:
            raise ValueError(
                f"Circle {self.id!r} contains non-member entities: {', '.join(invalid)}"
            )
        if len(self.tags) != len(set(self.tags)):
            raise ValueError(f"Circle {self.id!r} contains duplicate tags.")
        return self
