"""Created: 2026-09-24

Purpose: Defines the common Circle Member and non-agent Component contracts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easy_agents.galaxy.enums import ComponentKind, LifecycleStatus, MemberKind
from easy_agents.galaxy.identity import CircleId, EntityId


class CircleMember(BaseModel):
    """Base contract for anything assigned to one or more Circles.

    A Circle Member is either a Planet or a Component. The class holds only
    stable identity and placement metadata; execution belongs to runtime
    services, not to this data model.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: EntityId
    display_name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4_000)
    member_kind: MemberKind
    circle_ids: tuple[CircleId, ...] = Field(min_length=1)
    status: LifecycleStatus = LifecycleStatus.PROPOSED
    tags: tuple[str, ...] = ()
    legacy_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_unique_values(self) -> "CircleMember":
        """Rejects ambiguous duplicate membership, tags, and compatibility IDs."""

        for label, values in (
            ("circle", self.circle_ids),
            ("tag", self.tags),
            ("legacy identifier", self.legacy_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{self.id!r} contains duplicate {label} values.")
        return self


class Component(CircleMember):
    """Represents a non-agent resource that enables or constrains Planet work.

    Components do not own Missions, receive Work Orders, or make independent
    decisions. Examples include capabilities, Vaults, Playbooks, Gates, models,
    services, and the specialized :class:`~easy_agents.galaxy.Satellite` class.
    """

    member_kind: Literal[MemberKind.COMPONENT] = MemberKind.COMPONENT
    component_kind: ComponentKind
    capability_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_capability_ids(self) -> "Component":
        """Rejects duplicate capability bindings."""

        if len(self.capability_ids) != len(set(self.capability_ids)):
            raise ValueError(f"Component {self.id!r} contains duplicate capabilities.")
        return self
