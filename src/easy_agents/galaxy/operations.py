"""Created: 2026-09-24

Purpose: Defines canonical Gate, Vault, Observatory, and Mission Log contracts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from easy_agents.galaxy.enums import ComponentKind
from easy_agents.galaxy.identity import Identifier
from easy_agents.galaxy.members import Component


class Gate(Component):
    """A deterministic policy or human-approval boundary.

    Gates constrain effects; they never execute a Mission and never delegate
    authority. Runtime policy evaluates them immediately before a protected
    operation.
    """

    component_kind: Literal[ComponentKind.GATE] = ComponentKind.GATE
    allowed_effects: tuple[str, ...] = ("read",)
    approval_effects: tuple[str, ...] = ()
    denied_effects: tuple[str, ...] = ()
    external_network: Literal["deny", "approval", "allow"] = "deny"


class Vault(Component):
    """A scoped, auditable memory or data-isolation boundary."""

    component_kind: Literal[ComponentKind.VAULT] = ComponentKind.VAULT
    sensitivity: Literal["temporary", "private", "confidential", "sensitive"]
    writable: bool = True
    retention: str = Field(default="user-controlled", min_length=1, max_length=256)


class Observatory(BaseModel):
    """Describes the monitoring and replay service for one Galaxy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    galaxy_id: Identifier
    event_schema_version: int = Field(default=1, ge=1)
    live_stream_enabled: bool = True
    replay_enabled: bool = True
    redaction_enabled: bool = True


class MissionLogEntry(BaseModel):
    """Stores one redacted, correlated event in a Mission Log."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=160)
    entity_id: str = Field(min_length=1, max_length=256)
    summary: str = Field(max_length=4_000)
    correlation_id: str = Field(min_length=1, max_length=256)
    causation_id: str | None = Field(default=None, max_length=256)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MissionLog(BaseModel):
    """Contains ordered redacted events for one Mission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: Identifier
    entries: tuple[MissionLogEntry, ...] = ()
