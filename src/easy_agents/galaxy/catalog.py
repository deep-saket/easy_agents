"""Created: 2026-09-24

Purpose: Loads and saves versioned Galaxy snapshots without runtime side effects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from easy_agents.galaxy.registry import GalaxyRegistry
from easy_agents.galaxy.schemas import GalaxySnapshotV2


def load_galaxy(path: str | Path) -> GalaxyRegistry:
    """Loads and validates a version-2 Galaxy YAML file.

    Args:
        path: UTF-8 YAML file containing a ``GalaxySnapshotV2`` mapping.

    Returns:
        A fully cross-reference-validated GalaxyRegistry.

    Raises:
        ValueError: If YAML is not a mapping, uses an unsupported version, or
            violates any domain invariant.
    """

    return load_galaxy_text(Path(path).read_text(encoding="utf-8"))


def load_galaxy_text(value: str) -> GalaxyRegistry:
    """Loads a version-2 Galaxy snapshot from YAML text."""

    payload = yaml.safe_load(value)
    if not isinstance(payload, dict):
        raise ValueError("Galaxy snapshot must be a YAML mapping.")
    if payload.get("version") != 2:
        raise ValueError(
            f"Unsupported Galaxy snapshot version: {payload.get('version')!r}; expected 2."
        )
    return GalaxySnapshotV2.model_validate(payload).to_registry()


def dump_galaxy(registry: GalaxyRegistry) -> str:
    """Serializes a registry as deterministic version-2 YAML text."""

    payload: dict[str, Any] = GalaxySnapshotV2.from_registry(registry).model_dump(
        mode="json"
    )
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def save_galaxy(registry: GalaxyRegistry, path: str | Path) -> None:
    """Writes a validated registry to a UTF-8 version-2 YAML file.

    The function overwrites only the exact file passed by the caller. Production
    migration tooling should write a sibling file and use its documented backup
    and rollback flow before replacing user data.
    """

    Path(path).write_text(dump_galaxy(registry), encoding="utf-8")
