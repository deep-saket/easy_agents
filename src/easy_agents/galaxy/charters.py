"""Created: 2026-09-24

Purpose: Defines the declarative Charter shared by every Planet class.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easy_agents.galaxy.identity import Identifier


class Charter(BaseModel):
    """Declares a Planet's bounded purpose, dependencies, and allowed effects.

    A Charter describes authority; it does not grant authority by itself. The
    runtime intersects these declarations with the Mission's Permission Grant
    and applicable Gates before each effect.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    purpose: str = Field(min_length=3, max_length=4_000)
    capability_ids: tuple[Identifier, ...] = ()
    satellite_ids: tuple[Identifier, ...] = ()
    vault_ids: tuple[Identifier, ...] = Field(min_length=1)
    playbook_ids: tuple[Identifier, ...] = Field(min_length=1)
    gate_ids: tuple[Identifier, ...] = Field(min_length=1)
    model_ids: tuple[Identifier, ...] = ()
    allowed_effects: tuple[str, ...] = ("read",)
    network_access: Literal["deny", "approval", "allow"] = "deny"
    prohibited_actions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_bindings(self) -> "Charter":
        """Rejects duplicate dependency and effect declarations."""

        for label, values in (
            ("capability", self.capability_ids),
            ("Satellite", self.satellite_ids),
            ("Vault", self.vault_ids),
            ("Playbook", self.playbook_ids),
            ("Gate", self.gate_ids),
            ("model", self.model_ids),
            ("effect", self.allowed_effects),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Charter contains duplicate {label} values.")
        return self
