"""Loading and query helpers for the constellation directory."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from easy_agents.constellation.models import (
    CapabilityDefinition,
    ConstellationCatalog,
    GuildDefinition,
    SpecialistDefinition,
)


class ConstellationDirectory:
    """Validated, read-only view of the configured constellation roster."""

    def __init__(self, catalog: ConstellationCatalog) -> None:
        self.catalog = catalog
        self.guilds = {guild.id: guild for guild in catalog.guilds}
        self.capabilities = {capability.id: capability for capability in catalog.capabilities}
        self.specialists = {specialist.id: specialist for specialist in catalog.specialists}

    @classmethod
    def default(cls) -> "ConstellationDirectory":
        """Loads the packaged starter constellation."""

        catalog_text = (
            resources.files("easy_agents.constellation")
            .joinpath("default_catalog.yaml")
            .read_text(encoding="utf-8")
        )
        return cls.from_yaml_text(catalog_text)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ConstellationDirectory":
        """Loads a catalog from a user-supplied YAML file."""

        return cls.from_yaml_text(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def from_yaml_text(cls, value: str) -> "ConstellationDirectory":
        """Loads a catalog from YAML text and validates all references."""

        payload = yaml.safe_load(value)
        if not isinstance(payload, dict):
            raise ValueError("Constellation catalog must be a YAML mapping.")
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "ConstellationDirectory":
        """Loads a catalog from an already parsed mapping."""

        return cls(ConstellationCatalog.model_validate(payload))

    def owners_of(self, capability_id: str) -> list[SpecialistDefinition]:
        """Returns active and proposed specialists declaring a capability."""

        return [
            specialist
            for specialist in self.specialists.values()
            if capability_id in specialist.capability_ids
        ]

    def capabilities_for(self, specialist_id: str) -> list[CapabilityDefinition]:
        """Returns capabilities declared by one specialist."""

        specialist = self.specialists[specialist_id]
        return [self.capabilities[item] for item in specialist.capability_ids]

    def guilds_for(self, specialist_id: str) -> list[GuildDefinition]:
        """Returns every guild joined by one specialist."""

        specialist = self.specialists[specialist_id]
        return [self.guilds[item] for item in specialist.guilds]
