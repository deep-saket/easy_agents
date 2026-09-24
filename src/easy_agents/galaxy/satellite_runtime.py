"""Created: 2026-09-24

Purpose: Authorizes Satellite invocations before delegating to ToolExecutor.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from easy_agents.galaxy.identity import PlanetId
from easy_agents.galaxy.missions import PermissionGrant
from easy_agents.galaxy.registry import GalaxyRegistry


@runtime_checkable
class ToolExecutorLike(Protocol):
    """Structural subset used from the existing technical ToolExecutor."""

    def execute(self, tool_name: str, input: dict[str, Any]) -> dict[str, Any]:
        """Executes one validated technical tool call."""


class SatelliteCall(BaseModel):
    """Carries one bounded Satellite invocation request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    planet_id: PlanetId
    satellite_id: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_verified: bool = False


class SatelliteExecutor:
    """Enforces Charter, grant, network, approval, and payload constraints.

    The class deliberately delegates schema validation, logging, memory capture,
    and concrete execution to the existing ``ToolExecutor``. It performs no
    automatic retries; retry policy belongs to a durable runtime that can prove
    idempotency and cancellation behavior.
    """

    def __init__(
        self,
        registry: GalaxyRegistry,
        executor: ToolExecutorLike,
        *,
        max_payload_bytes: int = 64 * 1024,
    ) -> None:
        """Initializes an authorization wrapper over a technical executor.

        Args:
            registry: Canonical source of Planets and Satellites.
            executor: Existing ToolExecutor-compatible implementation.
            max_payload_bytes: Maximum JSON-encoded argument payload.
        """

        if max_payload_bytes < 1:
            raise ValueError("max_payload_bytes must be positive")
        self.registry = registry
        self.executor = executor
        self.max_payload_bytes = max_payload_bytes

    def invoke(
        self,
        call: SatelliteCall,
        *,
        grant: PermissionGrant,
    ) -> dict[str, Any]:
        """Authorizes and executes one Satellite call.

        Args:
            call: Planet, Satellite, arguments, and verified approval state.
            grant: Permission Grant attached to the current Work Order.

        Returns:
            The technical ToolExecutor result.

        Raises:
            PermissionError: If Charter, grant, effects, approval, or network
                policy denies the invocation.
            ValueError: If the payload exceeds the configured size limit.
        """

        planet = self.registry.get_planet(call.planet_id)
        satellite = self.registry.satellites.get(call.satellite_id)
        if satellite is None:
            raise KeyError(f"Unknown Satellite: {call.satellite_id}")
        if satellite.id not in planet.charter.satellite_ids:
            raise PermissionError(
                f"Planet {planet.id!r} Charter does not include Satellite {satellite.id!r}."
            )
        if satellite.id not in grant.satellite_ids:
            raise PermissionError(f"Permission Grant denies Satellite {satellite.id!r}.")
        if not set(satellite.effects) <= set(grant.effects):
            raise PermissionError(
                f"Permission Grant denies effects required by Satellite {satellite.id!r}."
            )
        if satellite.approval_required and not call.approval_verified:
            raise PermissionError(f"Satellite {satellite.id!r} requires approval.")
        if satellite.network_required:
            if not grant.allow_network:
                raise PermissionError(f"Permission Grant denies network access.")
            if planet.charter.network_access == "deny":
                raise PermissionError(f"Planet {planet.id!r} Charter denies network access.")
            if planet.charter.network_access == "approval" and not call.approval_verified:
                raise PermissionError(f"Planet {planet.id!r} requires network approval.")
        encoded = json.dumps(call.arguments, sort_keys=True, default=str).encode("utf-8")
        if len(encoded) > self.max_payload_bytes:
            raise ValueError(
                f"Satellite payload exceeds {self.max_payload_bytes} byte limit."
            )
        return self.executor.execute(satellite.tool_id, call.arguments)
