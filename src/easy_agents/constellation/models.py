"""Typed contracts for the personal-agent constellation and feature intake."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RiskLevel(str, Enum):
    """Policy risk assigned to a capability or proposed change."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class LifecycleStatus(str, Enum):
    """Lifecycle states used before a specialist can become active."""

    PROPOSED = "proposed"
    SCAFFOLDED = "scaffolded"
    SANDBOXED = "sandboxed"
    EVALUATED = "evaluated"
    APPROVED = "approved"
    ACTIVE = "active"
    QUARANTINED = "quarantined"
    RETIRED = "retired"


class FeatureDecision(str, Enum):
    """Possible outcomes of feature fit analysis."""

    REUSE = "reuse_existing"
    COMPOSE = "compose_playbook"
    EXTEND = "extend_specialist"
    CREATE = "create_specialist"


class GuildDefinition(BaseModel):
    """A user-visible domain group; specialists may join multiple guilds."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    display_name: str
    purpose: str
    tags: list[str] = Field(default_factory=list)


class CapabilityDefinition(BaseModel):
    """A typed operation that one or more specialists may expose."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    display_name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=lambda: ["read"])
    risk: RiskLevel = RiskLevel.LOW
    network_required: bool = False
    approval_required: bool = False


class SpecialistDefinition(BaseModel):
    """A narrow agent charter recorded in the constellation directory."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    display_name: str
    purpose: str
    guilds: list[str] = Field(min_length=1)
    capability_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    liaison: bool = False
    status: LifecycleStatus = LifecycleStatus.ACTIVE


class ConstellationCatalog(BaseModel):
    """Versioned directory of guilds, capabilities, and specialists."""

    version: Literal[1] = 1
    guilds: list[GuildDefinition]
    capabilities: list[CapabilityDefinition]
    specialists: list[SpecialistDefinition]

    @model_validator(mode="after")
    def validate_references(self) -> "ConstellationCatalog":
        """Reject duplicate identifiers and dangling guild/capability links."""

        guild_ids = [guild.id for guild in self.guilds]
        capability_ids = [capability.id for capability in self.capabilities]
        specialist_ids = [specialist.id for specialist in self.specialists]
        for kind, identifiers in (
            ("guild", guild_ids),
            ("capability", capability_ids),
            ("specialist", specialist_ids),
        ):
            duplicates = sorted(
                {value for value in identifiers if identifiers.count(value) > 1}
            )
            if duplicates:
                raise ValueError(f"Duplicate {kind} identifiers: {', '.join(duplicates)}")

        known_guilds = set(guild_ids)
        known_capabilities = set(capability_ids)
        for specialist in self.specialists:
            missing_guilds = sorted(set(specialist.guilds) - known_guilds)
            missing_capabilities = sorted(
                set(specialist.capability_ids) - known_capabilities
            )
            if missing_guilds:
                raise ValueError(
                    f"Specialist {specialist.id!r} references unknown guilds: "
                    f"{', '.join(missing_guilds)}"
                )
            if missing_capabilities:
                raise ValueError(
                    f"Specialist {specialist.id!r} references unknown capabilities: "
                    f"{', '.join(missing_capabilities)}"
                )
        return self


class FeatureRequest(BaseModel):
    """Natural-language feature request submitted to the Feature Architect."""

    feature: str = Field(min_length=3)
    desired_outcome: str | None = None
    constraints: list[str] = Field(default_factory=list)
    domain_hints: list[str] = Field(default_factory=list)


class DirectoryMatch(BaseModel):
    """Explainable match against a directory entry."""

    id: str
    display_name: str
    score: float = Field(ge=0.0, le=1.0)
    matched_terms: list[str] = Field(default_factory=list)


class DraftCharter(BaseModel):
    """Non-runnable proposed specialist produced when no good fit exists."""

    id: str
    display_name: str
    mission: str
    guilds: list[str]
    proposed_capabilities: list[str]
    requested_permissions: list[str] = Field(default_factory=list)
    risk: RiskLevel
    status: LifecycleStatus = LifecycleStatus.PROPOSED


class FeatureProposal(BaseModel):
    """Auditable result of feature fit analysis."""

    proposal_id: str
    request: FeatureRequest
    decision: FeatureDecision
    confidence: float = Field(ge=0.0, le=1.0)
    inferred_guilds: list[str] = Field(default_factory=list)
    requested_effects: list[str] = Field(default_factory=list)
    risk: RiskLevel
    network_required: bool
    matched_specialists: list[DirectoryMatch] = Field(default_factory=list)
    matched_capabilities: list[DirectoryMatch] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    requires_human_approval: bool
    safe_to_auto_scaffold: bool
    draft_charter: DraftCharter | None = None
    next_steps: list[str] = Field(default_factory=list)
