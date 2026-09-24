"""Created: 2026-09-24

Purpose: Provides validated identifiers and typed references for Galaxy entities.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from easy_agents.galaxy.enums import EntityKind


Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    ),
]
"""A stable lowercase identifier safe for catalogs, URLs, and event payloads."""

EntityId = Identifier
GalaxyId = Identifier
CircleId = Identifier
PlanetId = Identifier
ComponentId = Identifier
ConstellationId = Identifier
RogueStarId = Identifier


class EntityRef(BaseModel):
    """References one canonical entity without embedding the entity itself.

    References prevent circular persistence structures. A registry resolves a
    reference and validates that the target exists and has the declared kind.
    ``legacy_id`` may preserve a stable v1 identifier such as
    ``specialist:personal_steward`` during migration.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    kind: EntityKind
    id: EntityId
    legacy_id: str | None = Field(default=None, max_length=256)

    @property
    def canonical_id(self) -> str:
        """Returns the globally readable ``kind:id`` representation."""

        return f"{self.kind.value}:{self.id}"
