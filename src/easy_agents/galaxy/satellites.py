"""Created: 2026-09-24

Purpose: Defines Satellite metadata and adapters over the existing tool system.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import Field, model_validator

from easy_agents.galaxy.enums import ComponentKind
from easy_agents.galaxy.identity import Identifier
from easy_agents.galaxy.members import Component


@runtime_checkable
class ToolLike(Protocol):
    """Minimal structural contract required from an existing tool object."""

    name: str
    description: str
    input_schema: type[Any]
    output_schema: type[Any]


class Satellite(Component):
    """A bounded callable Component backed by a technical tool implementation.

    ``tool_id`` intentionally preserves the current tool registry name. A
    Satellite describes policy and operability metadata; actual execution stays
    in ``ToolExecutor`` so validation, logging, and memory capture are reused.
    """

    component_kind: Literal[ComponentKind.SATELLITE] = ComponentKind.SATELLITE
    tool_id: Identifier
    effects: tuple[str, ...] = ("read",)
    input_schema_name: str = Field(default="unknown", min_length=1, max_length=256)
    output_schema_name: str = Field(default="unknown", min_length=1, max_length=256)
    network_required: bool = False
    approval_required: bool = False
    idempotent: bool = True
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=3_600.0)
    max_attempts: int = Field(default=1, ge=1, le=5)

    @model_validator(mode="after")
    def validate_effects(self) -> "Satellite":
        """Rejects duplicate effects and unsafe implicit retries."""

        if len(self.effects) != len(set(self.effects)):
            raise ValueError(f"Satellite {self.id!r} contains duplicate effects.")
        if not self.idempotent and self.max_attempts != 1:
            raise ValueError(
                "A non-idempotent Satellite cannot enable automatic retries."
            )
        return self

    @classmethod
    def from_tool(
        cls,
        tool: ToolLike,
        *,
        circle_ids: tuple[str, ...],
        effects: tuple[str, ...] = ("read",),
        **overrides: Any,
    ) -> "Satellite":
        """Builds Satellite metadata from an existing ``BaseTool``-like object.

        Args:
            tool: Registered tool exposing name, description, and Pydantic
                input/output schemas.
            circle_ids: Circles whose Planets may be given an Orbit to this
                Satellite. Runtime policy still authorizes each invocation.
            effects: Declared effect categories used by policy evaluation.
            **overrides: Explicit Satellite fields such as approval or timeout
                settings.

        Returns:
            A validated immutable Satellite descriptor.

        Raises:
            TypeError: If ``tool`` does not satisfy the required tool contract.
        """

        if not isinstance(tool, ToolLike):
            raise TypeError("tool must expose the BaseTool metadata contract")
        return cls(
            id=tool.name,
            display_name=tool.name.replace("_", " ").title(),
            description=tool.description,
            circle_ids=circle_ids,
            tool_id=tool.name,
            effects=effects,
            input_schema_name=tool.input_schema.__name__,
            output_schema_name=tool.output_schema.__name__,
            legacy_ids=(f"tool:{tool.name}",),
            **overrides,
        )
