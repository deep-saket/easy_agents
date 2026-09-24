"""Created: 2026-09-24

Purpose: Defines canonical work, routing, delegation, and result contracts.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easy_agents.galaxy.enums import EntityKind, MissionStatus
from easy_agents.galaxy.identity import CircleId, EntityRef, GalaxyId, Identifier, PlanetId


def _mission_id() -> str:
    """Creates a collision-resistant Mission identifier with a valid prefix."""

    return f"mission-{uuid4().hex}"


def _work_order_id() -> str:
    """Creates a collision-resistant Work Order identifier."""

    return f"order-{uuid4().hex}"


class MissionBudget(BaseModel):
    """Bounds resources a Mission may consume across all selected Planets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timeout_seconds: float = Field(default=300.0, gt=0.0, le=86_400.0)
    max_planets: int = Field(default=1, ge=1, le=16)
    max_satellite_calls: int = Field(default=20, ge=0, le=10_000)
    max_model_tokens: int = Field(default=8_192, ge=0, le=10_000_000)
    max_delegation_depth: int = Field(default=2, ge=0, le=8)


class Mission(BaseModel):
    """Represents a user goal accepted through a Portal and Wormhole.

    Mission inputs describe requested authority, not granted authority. Runtime
    policy creates the actual Permission Grant after routing.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: Identifier = Field(default_factory=_mission_id)
    objective: str = Field(min_length=3, max_length=20_000)
    galaxy_id: GalaxyId | None = None
    preferred_circle_id: CircleId | None = None
    preferred_planet_id: PlanetId | None = None
    requested_effects: tuple[str, ...] = ("read",)
    requested_vault_ids: tuple[Identifier, ...] = ()
    allow_network: bool = False
    team_size: int = Field(default=1, ge=1, le=16)
    context: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    budget: MissionBudget = Field(default_factory=MissionBudget)

    @model_validator(mode="after")
    def validate_request(self) -> "Mission":
        """Rejects duplicate request declarations and oversized context."""

        if len(self.requested_effects) != len(set(self.requested_effects)):
            raise ValueError("Mission contains duplicate requested effects.")
        if len(self.requested_vault_ids) != len(set(self.requested_vault_ids)):
            raise ValueError("Mission contains duplicate requested Vaults.")
        if len(self.context) > 128:
            raise ValueError("Mission context exceeds the 128-entry safety limit.")
        if self.team_size > self.budget.max_planets:
            raise ValueError("Mission team_size exceeds its max_planets budget.")
        return self


class PermissionGrant(BaseModel):
    """Represents authority that can only narrow during execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    effects: tuple[str, ...] = ()
    vault_ids: tuple[Identifier, ...] = ()
    satellite_ids: tuple[Identifier, ...] = ()
    rogue_star_ids: tuple[Identifier, ...] = ()
    allow_network: bool = False

    def narrowed_to(
        self,
        *,
        effects: tuple[str, ...] | None = None,
        vault_ids: tuple[Identifier, ...] | None = None,
        satellite_ids: tuple[Identifier, ...] | None = None,
        rogue_star_ids: tuple[Identifier, ...] | None = None,
        allow_network: bool | None = None,
    ) -> "PermissionGrant":
        """Intersects this grant with a child scope.

        Args:
            effects: Effects declared by the child Charter or Work Order.
            vault_ids: Vaults declared by the child.
            satellite_ids: Satellites declared by the child.
            rogue_star_ids: Rogue Stars declared by the child.
            allow_network: Child network request. ``True`` cannot override a
                parent grant that denied network access.

        Returns:
            A new immutable grant containing only parent-authorized values.
        """

        def intersect(parent: tuple[str, ...], child: tuple[str, ...] | None) -> tuple[str, ...]:
            """Preserves parent order while intersecting an optional child scope."""

            if child is None:
                return parent
            return tuple(item for item in parent if item in set(child))

        return PermissionGrant(
            effects=intersect(self.effects, effects),
            vault_ids=intersect(self.vault_ids, vault_ids),
            satellite_ids=intersect(self.satellite_ids, satellite_ids),
            rogue_star_ids=intersect(self.rogue_star_ids, rogue_star_ids),
            allow_network=(
                self.allow_network
                if allow_network is None
                else self.allow_network and allow_network
            ),
        )

    def is_subset_of(self, parent: "PermissionGrant") -> bool:
        """Returns whether this grant stays within a parent grant."""

        return (
            set(self.effects) <= set(parent.effects)
            and set(self.vault_ids) <= set(parent.vault_ids)
            and set(self.satellite_ids) <= set(parent.satellite_ids)
            and set(self.rogue_star_ids) <= set(parent.rogue_star_ids)
            and (not self.allow_network or parent.allow_network)
        )


class Trajectory(BaseModel):
    """Records the explainable Wormhole → Galaxy → Circle → Planet route."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: Identifier
    wormhole_id: Identifier = "wormhole"
    galaxy_id: GalaxyId
    circle_ids: tuple[CircleId, ...] = Field(min_length=1)
    planet_ids: tuple[PlanetId, ...] = Field(min_length=1)
    matched_terms: tuple[str, ...] = ()

    @property
    def path(self) -> tuple[EntityRef, ...]:
        """Returns the canonical ordered hops used for display and tracing."""

        return (
            EntityRef(kind=EntityKind.WORMHOLE, id=self.wormhole_id),
            EntityRef(kind=EntityKind.GALAXY, id=self.galaxy_id),
            *(EntityRef(kind=EntityKind.CIRCLE, id=item) for item in self.circle_ids),
            *(EntityRef(kind=EntityKind.PLANET, id=item) for item in self.planet_ids),
        )


class Crew(BaseModel):
    """Temporary set of Planets collaborating on one Mission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: Identifier
    planet_ids: tuple[PlanetId, ...] = Field(min_length=2, max_length=16)

    @model_validator(mode="after")
    def validate_unique_planets(self) -> "Crew":
        """Rejects duplicate Crew membership."""

        if len(self.planet_ids) != len(set(self.planet_ids)):
            raise ValueError("Crew contains duplicate Planets.")
        return self


class WorkOrder(BaseModel):
    """Carries a bounded delegation from a Mission to one Planet."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: Identifier = Field(default_factory=_work_order_id)
    mission_id: Identifier
    planet_id: PlanetId
    objective: str = Field(min_length=3, max_length=20_000)
    permission_grant: PermissionGrant
    parent_order_id: Identifier | None = None
    delegation_depth: int = Field(default=0, ge=0, le=8)
    correlation_id: str = Field(min_length=1, max_length=256)
    causation_id: str | None = Field(default=None, max_length=256)

    def delegate(
        self,
        *,
        planet_id: PlanetId,
        permission_grant: PermissionGrant,
        max_depth: int,
    ) -> "WorkOrder":
        """Creates a child Work Order after monotonic permission validation.

        Args:
            planet_id: Child Planet receiving the order.
            permission_grant: Already narrowed grant for the child.
            max_depth: Mission or coordinating Planet delegation limit.

        Returns:
            A validated child Work Order linked to this order.

        Raises:
            ValueError: If depth is exhausted, the target is unchanged, or the
                child attempts to widen authority.
        """

        if planet_id == self.planet_id:
            raise ValueError("A Work Order cannot delegate directly to the same Planet.")
        if self.delegation_depth >= max_depth:
            raise ValueError("Maximum delegation depth has been reached.")
        if not permission_grant.is_subset_of(self.permission_grant):
            raise ValueError("Delegated permissions cannot widen the parent grant.")
        return WorkOrder(
            mission_id=self.mission_id,
            planet_id=planet_id,
            objective=self.objective,
            permission_grant=permission_grant,
            parent_order_id=self.id,
            delegation_depth=self.delegation_depth + 1,
            correlation_id=self.correlation_id,
            causation_id=self.id,
        )


class FlightPlan(BaseModel):
    """Resolves one Playbook into ordered, bounded execution steps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    playbook_id: Identifier
    step_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_steps(self) -> "FlightPlan":
        """Rejects duplicate execution steps."""

        if len(self.step_ids) != len(set(self.step_ids)):
            raise ValueError("Flight Plan contains duplicate steps.")
        return self


class PlanetRunResult(BaseModel):
    """Captures one Planet's auditable response to a Work Order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: Identifier
    work_order_id: Identifier
    planet_id: PlanetId
    status: MissionStatus
    response: str
    artifacts: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class GalaxyMissionResult(BaseModel):
    """Aggregates routing and all Planet results for one Mission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: Identifier
    status: MissionStatus
    trajectory: Trajectory
    results: tuple[PlanetRunResult, ...]
    synthesis: str
