"""Canonical contracts for declarative Specialists and bounded Missions."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


Identifier = str


class SpecialistStatus(str, Enum):
    """Runtime lifecycle visible to selection and execution policy."""

    ACTIVE = "active"
    SANDBOXED = "sandboxed"
    QUARANTINED = "quarantined"
    RETIRED = "retired"


class MissionStatus(str, Enum):
    """Outcome of one bounded Specialist or team execution."""

    PLANNED = "planned"
    COMPLETED = "completed"
    AWAITING_APPROVAL = "awaiting_approval"
    BLOCKED = "blocked"
    FAILED = "failed"


class StepKind(str, Enum):
    """Reusable step families supported by the first fleet runtime."""

    INSPECT = "inspect"
    REASON = "reason"
    TOOL = "tool"
    DELEGATE = "delegate"
    GATE = "gate"
    SYNTHESIZE = "synthesize"
    RECORD = "record"


class PlaybookStep(BaseModel):
    """One bounded step inside a reusable Playbook."""

    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    title: str
    instruction: str
    kind: StepKind = StepKind.REASON
    effects: list[str] = Field(default_factory=lambda: ["read"])
    optional: bool = False


class PlaybookSpec(BaseModel):
    """Versioned workflow shared by multiple Specialist Charters."""

    version: Literal[1] = 1
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    display_name: str
    description: str
    steps: list[PlaybookStep] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    max_steps: int = Field(default=12, ge=1, le=64)

    @model_validator(mode="after")
    def validate_step_ids(self) -> "PlaybookSpec":
        identifiers = [step.id for step in self.steps]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"Playbook {self.id!r} has duplicate step identifiers.")
        if len(self.steps) > self.max_steps:
            raise ValueError(
                f"Playbook {self.id!r} has {len(self.steps)} steps, above max_steps={self.max_steps}."
            )
        return self


class MemoryScopeSpec(BaseModel):
    """A named data boundary available to selected Specialists."""

    version: Literal[1] = 1
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    display_name: str
    description: str
    sensitivity: Literal["temporary", "private", "confidential", "sensitive"]
    writable: bool = True
    dormant: bool = False
    retention: str = "user-controlled"


class PolicyProfile(BaseModel):
    """Central least-privilege rules applied before a Playbook runs."""

    version: Literal[1] = 1
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    display_name: str
    description: str
    allowed_effects: list[str] = Field(default_factory=lambda: ["read", "write", "compute", "draft"])
    approval_effects: list[str] = Field(default_factory=list)
    denied_effects: list[str] = Field(default_factory=list)
    external_network: Literal["deny", "approval", "allow"] = "deny"
    blocked_terms: list[str] = Field(default_factory=list)


class SpecialistManifest(BaseModel):
    """Runnable Charter compiled from the Constellation graph."""

    version: Literal[1] = 1
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    display_name: str
    purpose: str
    guilds: list[str] = Field(min_length=1)
    playbook_ids: list[str] = Field(min_length=1)
    capability_ids: list[str] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list)
    memory_scope_ids: list[str] = Field(min_length=1)
    policy_ids: list[str] = Field(min_length=1)
    model_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: SpecialistStatus
    source_status: str


class MissionRequest(BaseModel):
    """User or parent-agent request to the fleet runtime."""

    objective: str = Field(min_length=3)
    specialist_id: str | None = None
    preferred_playbook_id: str | None = None
    memory_scope: str | None = None
    requested_effects: list[str] = Field(default_factory=lambda: ["read"])
    approved_effects: list[str] = Field(default_factory=list)
    allow_network: bool = False
    team_size: int = Field(default=1, ge=1, le=8)
    context: dict[str, Any] = Field(default_factory=dict)


class PermissionGrant(BaseModel):
    """Authority that can only narrow as Missions delegate Work orders."""

    effects: list[str]
    memory_scopes: list[str]
    allow_network: bool = False

    def narrowed_for(self, manifest: SpecialistManifest) -> "PermissionGrant":
        """Intersects this grant with a child Charter's declared scopes."""

        return PermissionGrant(
            effects=list(self.effects),
            memory_scopes=sorted(set(self.memory_scopes) & set(manifest.memory_scope_ids)),
            allow_network=self.allow_network,
        )


class WorkOrder(BaseModel):
    """Typed delegation envelope between a Mission and one Specialist."""

    id: str
    mission_id: str
    parent_order_id: str | None = None
    specialist_id: str
    objective: str
    playbook_id: str
    permissions: PermissionGrant


class ApprovalRequest(BaseModel):
    """Exact effects that need a human decision before execution."""

    id: str
    mission_id: str
    specialist_id: str
    effects: list[str]
    rationale: str
    status: Literal["pending"] = "pending"


class StepResult(BaseModel):
    """Auditable result of one compiled Playbook step."""

    step_id: str
    title: str
    kind: StepKind
    status: Literal["planned", "completed", "blocked", "waiting"]
    summary: str
    effects: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    """Typed result returned by one Specialist."""

    run_id: str
    mission_id: str
    specialist_id: str
    specialist_name: str
    status: MissionStatus
    playbook_id: str
    response: str
    steps: list[StepResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approvals: list[ApprovalRequest] = Field(default_factory=list)
    used_model: str | None = None
    work_order: WorkOrder


class RouteCandidate(BaseModel):
    """Explainable Specialist candidate produced by lexical routing."""

    specialist_id: str
    display_name: str
    score: float = Field(ge=0.0, le=1.0)
    matched_terms: list[str] = Field(default_factory=list)
    status: SpecialistStatus
    guilds: list[str]


class FleetMissionResult(BaseModel):
    """Root Mission result containing one or more Specialist results."""

    mission_id: str
    objective: str
    status: MissionStatus
    routed_specialists: list[RouteCandidate]
    results: list[AgentResult]
    synthesis: str
    warnings: list[str] = Field(default_factory=list)
