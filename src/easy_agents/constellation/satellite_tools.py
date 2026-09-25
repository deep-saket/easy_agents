"""Created: 2026-09-25

Purpose: Plans and executes safe local Satellites for Wormhole Chat.

The module deliberately supports only capabilities that can run locally without
an account, network access, or an irreversible side effect.  It reuses the
canonical :class:`SatelliteExecutor` for authorization and the shared
``ToolExecutor`` for schema validation, logging, and concrete execution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from easy_agents.galaxy.missions import PermissionGrant
from easy_agents.galaxy.registry import GalaxyRegistry
from easy_agents.galaxy.satellite_runtime import SatelliteCall, SatelliteExecutor
from easy_agents.observability import EntityReference, Severity
from src.memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from src.memory.retrieval.retriever import LayeredMemoryRetriever
from src.memory.store import MemoryStore
from src.tools.executor import ToolExecutor
from src.tools.math import CalculateTool, UnitConvertTool
from src.tools.memory_search import MemorySearchTool
from src.tools.memory_write import MemoryWriteTool
from src.tools.registry import ToolRegistry


_UNIT_CONVERSION = re.compile(
    r"\b(?:convert\s+)?(?P<value>-?\d+(?:\.\d+)?)\s*"
    r"(?P<from>°?[a-zA-Z]+)\s+(?:to|into|in)\s+(?P<to>°?[a-zA-Z]+)\b",
    re.IGNORECASE,
)
_CALCULATION = re.compile(
    r"\b(?:calculate|compute|solve|what\s+is)\s+"
    r"(?P<expression>[0-9().\s+\-*/%]+)",
    re.IGNORECASE,
)
_MEMORY_WRITE = re.compile(
    r"^\s*(?:please\s+)?(?:remember(?:\s+that)?|save\s+(?:this\s+)?(?:to\s+)?memory)"
    r"\s*[:,-]?\s*(?P<fact>.+?)\s*$",
    re.IGNORECASE,
)
_MEMORY_SEARCH = (
    re.compile(r"\bwhat\s+do\s+you\s+remember\s+about\s+(?P<query>.+?)\s*[?.!]*$", re.IGNORECASE),
    re.compile(r"\bsearch\s+(?:my\s+)?memory\s+for\s+(?P<query>.+?)\s*[?.!]*$", re.IGNORECASE),
    re.compile(r"^\s*recall\s+(?P<query>.+?)\s*[?.!]*$", re.IGNORECASE),
)


class PlannedSatelliteCall(BaseModel):
    """One explicit, bounded local tool call selected from a user message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    satellite_id: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=300)


class LocalSatellitePlanner:
    """Recognizes explicit requests supported by deterministic local tools.

    The planner intentionally avoids guessing.  General reasoning continues to
    use Gemma, while exact arithmetic, unit conversion, and explicit memory
    commands are delegated to schema-validated Satellites.  Email, calls,
    notifications, purchases, and network tools are never selected here.
    """

    def plan(
        self,
        message: str,
        *,
        conversation_id: str,
        available_ids: frozenset[str],
    ) -> tuple[PlannedSatelliteCall, ...]:
        """Returns at most one unambiguous local Satellite call."""

        memory_write = _MEMORY_WRITE.search(message)
        if memory_write and "memory_write" in available_ids:
            fact = memory_write.group("fact").strip().rstrip(".")
            if fact:
                return (
                    PlannedSatelliteCall(
                        satellite_id="memory_write",
                        arguments={
                            "item": {
                                "type": "semantic",
                                "layer": "warm",
                                "scope": "agent_local",
                                "agent_id": "galaxy_chat",
                                "content": {"fact": fact},
                                "content_text": fact,
                                "source_type": "user",
                                "source_id": conversation_id,
                                "tags": ["wormhole_chat", conversation_id],
                                "confidence": 1.0,
                            }
                        },
                        reason="The user explicitly asked to remember a fact.",
                    ),
                )

        for pattern in _MEMORY_SEARCH:
            match = pattern.search(message)
            if match and "memory_search" in available_ids:
                query = match.group("query").strip().rstrip("?.!")
                if query:
                    return (
                        PlannedSatelliteCall(
                            satellite_id="memory_search",
                            arguments={
                                "query": query,
                                "filters": {
                                    "scope": "agent_local",
                                    "agent_id": "galaxy_chat",
                                },
                                "limit": 5,
                            },
                            reason="The user explicitly asked to retrieve local memory.",
                        ),
                    )

        conversion = _UNIT_CONVERSION.search(message)
        if conversion and "unit_convert" in available_ids:
            return (
                PlannedSatelliteCall(
                    satellite_id="unit_convert",
                    arguments={
                        "value": float(conversion.group("value")),
                        "from_unit": self._normalize_unit(conversion.group("from")),
                        "to_unit": self._normalize_unit(conversion.group("to")),
                    },
                    reason="The message contains an explicit supported unit conversion.",
                ),
            )

        calculation = _CALCULATION.search(message)
        if calculation and "calculate" in available_ids:
            expression = calculation.group("expression").strip().rstrip("?.!, ")
            if expression and any(operator in expression for operator in "+-*/%"):
                return (
                    PlannedSatelliteCall(
                        satellite_id="calculate",
                        arguments={"expression": expression},
                        reason="The message contains an explicit arithmetic expression.",
                    ),
                )
        return ()

    @staticmethod
    def _normalize_unit(value: str) -> str:
        """Normalizes common degree-symbol abbreviations for UnitConvertTool."""

        return value.lower().removeprefix("°")


@dataclass(slots=True)
class LocalSatelliteRuntime:
    """Reusable local-only Satellite planner and authorized executor."""

    galaxy_registry: GalaxyRegistry
    executor: SatelliteExecutor
    planner: LocalSatellitePlanner
    executable_ids: frozenset[str]
    event_recorder: Any | None = None

    def plan(self, message: str, *, conversation_id: str) -> tuple[PlannedSatelliteCall, ...]:
        """Plans an explicit call from the runtime's executable allow-list."""

        return self.planner.plan(
            message,
            conversation_id=conversation_id,
            available_ids=self.executable_ids,
        )

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
            result = self.executor.invoke(
                SatelliteCall(
                    planet_id=planet_id,
                    satellite_id=call.satellite_id,
                    arguments=call.arguments,
                ),
                grant=PermissionGrant(
                    effects=satellite.effects,
                    vault_ids=("long_term",),
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
) -> LocalSatelliteRuntime:
    """Builds the four safe local Satellites used by Wormhole Chat.

    Args:
        galaxy_registry: Canonical authorization registry.
        data_dir: Directory for durable local memory when ``persistent`` is
            true. Defaults to the repository ``data`` directory.
        event_recorder: Optional observability pipeline.
        persistent: Use DuckDB/JSONL layers. False uses isolated in-process
            layers for tests and embedded API factories.
    """

    root = data_dir or Path("data")
    if persistent:
        root.mkdir(parents=True, exist_ok=True)
        warm_layer: Any = WarmMemoryLayer(root / "galaxy_memory.duckdb")
        cold_layer: Any = ColdMemoryLayer(root / "galaxy_memory.jsonl")
    else:
        warm_layer = HotMemoryLayer(max_items=2_048)
        cold_layer = HotMemoryLayer(max_items=2_048)
    memory_store = MemoryStore(
        hot_layer=HotMemoryLayer(max_items=256),
        warm_layer=warm_layer,
        cold_layer=cold_layer,
        archive_after_days=90,
        default_scope="agent_local",
        agent_id="galaxy_chat",
    )
    registry = ToolRegistry()
    for tool in (
        CalculateTool(),
        UnitConvertTool(),
        MemorySearchTool(retriever=LayeredMemoryRetriever(memory_store)),
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
        planner=LocalSatellitePlanner(),
        executable_ids=executable_ids,
        event_recorder=event_recorder,
    )


__all__ = [
    "LocalSatellitePlanner",
    "LocalSatelliteRuntime",
    "PlannedSatelliteCall",
    "build_local_satellite_runtime",
]
