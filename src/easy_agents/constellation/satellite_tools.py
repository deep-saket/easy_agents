"""Created: 2026-09-25

Purpose: Plans and executes safe local Satellites for Wormhole Chat.

The module deliberately supports only capabilities that can run locally without
an account, network access, or an irreversible side effect.  It reuses the
canonical :class:`SatelliteExecutor` for authorization and the shared
``ToolExecutor`` for schema validation, logging, and concrete execution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from easy_agents.constellation.commons_runtime import (
    CommonsMemoryRetriever,
    CommonsRuntime,
    CommonsVaultStoreAdapter,
    VaultId,
    VaultMemoryCreate,
)
from easy_agents.galaxy.missions import PermissionGrant
from easy_agents.galaxy.registry import GalaxyRegistry
from easy_agents.galaxy.satellite_runtime import SatelliteCall, SatelliteExecutor
from easy_agents.observability import EntityReference, Severity
from src.tools.executor import ToolExecutor
from src.tools.math import CalculateTool, UnitConvertTool
from src.tools.memory_search import MemorySearchTool
from src.tools.memory_write import MemoryWriteTool
from src.tools.registry import ToolRegistry


class PlannedSatelliteCall(BaseModel):
    """One explicit, bounded local tool call selected from a user message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    satellite_id: str = Field(min_length=1, max_length=128)
    vault_id: VaultId | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=300)


@dataclass(slots=True)
class LocalSatelliteRuntime:
    """Reusable local-only authorized Satellite executor.

    Natural-language selection belongs to ``NaturalLanguagePlanner`` and is
    model-driven. This class deliberately performs no intent recognition.
    """

    galaxy_registry: GalaxyRegistry
    executor: SatelliteExecutor
    executable_ids: frozenset[str]
    commons_runtime: CommonsRuntime
    legacy_memories_migrated: int = 0
    event_recorder: Any | None = None

    def invoke(
        self,
        call: PlannedSatelliteCall,
        *,
        planet_id: str,
        mission_id: str,
    ) -> dict[str, Any]:
        """Authorizes, traces, and executes one local Satellite call."""

        satellite = self.galaxy_registry.satellites[call.satellite_id]
        started = perf_counter()
        self._record(
            "satellite.started",
            summary=f"Satellite {satellite.display_name} started",
            status="running",
            mission_id=mission_id,
            planet_id=planet_id,
            satellite_id=satellite.id,
            attributes={
                "argument_keys": sorted(call.arguments),
                "reason": call.reason,
            },
        )
        try:
            if call.vault_id is not None:
                planet = self.galaxy_registry.get_planet(planet_id)
                if call.vault_id not in planet.charter.vault_ids:
                    raise PermissionError(
                        f"Planet {planet_id!r} Charter does not include Vault "
                        f"{call.vault_id!r}."
                    )
            result = self.executor.invoke(
                SatelliteCall(
                    planet_id=planet_id,
                    satellite_id=call.satellite_id,
                    arguments=call.arguments,
                ),
                grant=PermissionGrant(
                    effects=satellite.effects,
                    vault_ids=((call.vault_id,) if call.vault_id is not None else ()),
                    satellite_ids=(satellite.id,),
                    allow_network=False,
                ),
            )
        except Exception as exc:
            self._record(
                "satellite.failed",
                summary=f"Satellite {satellite.display_name} failed",
                status="failed",
                severity=Severity.ERROR,
                mission_id=mission_id,
                planet_id=planet_id,
                satellite_id=satellite.id,
                duration_ms=round((perf_counter() - started) * 1000, 3),
                attributes={"error_type": type(exc).__name__},
            )
            raise
        self._record(
            "satellite.completed",
            summary=f"Satellite {satellite.display_name} completed",
            status="completed",
            mission_id=mission_id,
            planet_id=planet_id,
            satellite_id=satellite.id,
            duration_ms=round((perf_counter() - started) * 1000, 3),
            attributes={"output_keys": sorted(result.get("output", {}))},
        )
        return result

    def _record(
        self,
        event_type: str,
        *,
        summary: str,
        status: str,
        mission_id: str,
        planet_id: str,
        satellite_id: str,
        severity: Severity = Severity.INFO,
        duration_ms: float | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Records a bounded event without allowing tracing to break execution."""

        if self.event_recorder is None:
            return
        try:
            self.event_recorder.record(
                event_type,
                summary=summary,
                status=status,
                severity=severity,
                mission_id=mission_id,
                actor=EntityReference(kind="planet", id=planet_id),
                subject=EntityReference(kind="satellite", id=satellite_id),
                duration_ms=duration_ms,
                attributes=attributes or {},
            )
        except Exception:
            return


def build_local_satellite_runtime(
    galaxy_registry: GalaxyRegistry,
    *,
    data_dir: Path | None = None,
    event_recorder: Any | None = None,
    persistent: bool = True,
    commons_runtime: CommonsRuntime | None = None,
) -> LocalSatelliteRuntime:
    """Builds the four safe local Satellites used by Wormhole Chat.

    Args:
        galaxy_registry: Canonical authorization registry.
        data_dir: Directory for the durable Commons database when ``persistent``
            is true. Defaults to the repository ``data`` directory.
        event_recorder: Optional observability pipeline.
        persistent: Use SQLite persistence. False uses an isolated in-process
            database for tests and embedded API factories.
        commons_runtime: Optional shared Commons runtime. Supplying it keeps
            Chat tools and management APIs on the same Vault boundary.
    """

    root = data_dir or Path("data")
    active_commons = commons_runtime or CommonsRuntime(
        db_path=(root / "commons.db") if persistent else None,
        event_recorder=event_recorder,
    )
    legacy_memories_migrated = 0
    if persistent:
        legacy_memories_migrated = migrate_legacy_chat_memory(
            active_commons,
            root / "galaxy_memory.duckdb",
        )
    memory_store = CommonsVaultStoreAdapter(active_commons)
    registry = ToolRegistry()
    for tool in (
        CalculateTool(),
        UnitConvertTool(),
        MemorySearchTool(retriever=CommonsMemoryRetriever(memory_store)),
        MemoryWriteTool(store=memory_store),
    ):
        registry.register(tool)
    executable_ids = frozenset(tool.name for tool in registry.list_tools())
    return LocalSatelliteRuntime(
        galaxy_registry=galaxy_registry,
        executor=SatelliteExecutor(
            registry=galaxy_registry,
            executor=ToolExecutor(registry=registry),
        ),
        executable_ids=executable_ids,
        commons_runtime=active_commons,
        legacy_memories_migrated=legacy_memories_migrated,
        event_recorder=event_recorder,
    )


def migrate_legacy_chat_memory(runtime: CommonsRuntime, db_path: Path) -> int:
    """Imports legacy Chat memory into the Personal Vault once per record.

    The previous Chat runtime stored explicit memories in a standalone DuckDB
    file. Stable record identifiers make this migration idempotent. A missing,
    locked, or incompatible legacy file leaves the new runtime usable; the old
    file is never modified or deleted.
    """

    if not db_path.exists():
        return 0
    try:
        import duckdb

        connection = duckdb.connect(str(db_path), read_only=True)
        try:
            rows = connection.execute(
                """
                SELECT id, memory_type, content_text, source_type, source_id,
                       tags_json, created_at
                FROM memory_records
                WHERE scope = 'agent_local' AND agent_id = 'galaxy_chat'
                ORDER BY created_at
                """
            ).fetchall()
        finally:
            connection.close()
    except Exception:
        return 0

    migrated = 0
    for row in rows:
        memory_id, memory_type, content, source_type, source_id, tags, created_at = row
        if not content:
            continue
        try:
            runtime.get_memory("personal", str(memory_id))
            continue
        except KeyError:
            pass
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = []
        timestamp = created_at if isinstance(created_at, datetime) else datetime.now(UTC)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        runtime.add_memory(
            "personal",
            VaultMemoryCreate(
                content=str(content),
                memory_type=str(memory_type or "semantic"),
                tags=tuple(str(item) for item in (tags or [])),
                source_type=str(source_type or "user"),
                source_id=str(source_id) if source_id is not None else None,
            ),
            memory_id=str(memory_id),
            created_at=timestamp,
        )
        migrated += 1
    return migrated


__all__ = [
    "LocalSatelliteRuntime",
    "PlannedSatelliteCall",
    "build_local_satellite_runtime",
    "migrate_legacy_chat_memory",
]
