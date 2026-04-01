"""Created: 2026-04-01

Purpose: Implements config-driven write policies for the memory system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.memory.models import MemoryRecord
from src.memory.types import (
    EpisodicMemory,
    ErrorMemory,
    ErrorMemoryContent,
    ReflectionMemory,
    ReflectionMemoryContent,
    SemanticMemory,
    TaskMemory,
)


@dataclass(slots=True)
class MemoryPolicy:
    """Maps runtime events into typed memory records using policy config."""

    policy_path: Path = Path("config/memory_policies.yaml")
    _config: dict[str, Any] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._config = yaml.safe_load(self.policy_path.read_text(encoding="utf-8")) or {}

    def should_store(self, event: dict[str, Any]) -> bool:
        return event.get("event_type") in self._config.get("write_rules", {})

    def classify_type(self, event: dict[str, Any]) -> str:
        return self._rule_for(event).get("memory_type", "episodic")

    def classify_layer(self, event: dict[str, Any]) -> str:
        return self._rule_for(event).get("layer", "warm")

    def classify_scope(self, event: dict[str, Any]) -> str:
        return self._rule_for(event).get("scope", "agent_local")

    def build_item(self, event: dict[str, Any]) -> MemoryRecord:
        event_type = event.get("event_type")
        content = event.get("content", event)
        metadata = dict(event.get("metadata", {}))
        metadata.setdefault("event_type", event_type)
        metadata.setdefault("agent", event.get("agent", "unknown"))
        metadata.setdefault("agent_id", event.get("agent_id", metadata["agent"]))
        metadata.setdefault("tags", [])
        metadata.setdefault("source", self._infer_source(event_type))
        metadata.setdefault("source_type", metadata["source"])
        metadata.setdefault("source_id", event.get("source_id"))
        metadata.setdefault("priority", self._infer_priority(event_type))
        metadata.setdefault("confidence", event.get("confidence"))
        metadata.setdefault("importance", event.get("importance"))
        common = {
            "agent_id": event.get("agent_id", metadata["agent_id"]),
            "scope": self.classify_scope(event),
            "layer": self.classify_layer(event),
            "source_type": metadata.get("source_type"),
            "source_id": metadata.get("source_id"),
            "tags": list(metadata.get("tags", [])),
            "metadata": metadata,
            "importance": event.get("importance"),
            "confidence": event.get("confidence"),
        }
        if self.classify_type(event) == "error":
            return ErrorMemory(
                **common,
                content=ErrorMemoryContent(
                    input=event.get("input", {}),
                    output=event.get("output"),
                    error_type=event.get("error_type", "tool_failure"),
                    correction=event.get("correction"),
                    root_cause=event.get("root_cause", event.get("error")),
                    agent=common["agent_id"] or "unknown",
                ),
            )
        if self.classify_type(event) == "reflection":
            reflection_payload = content if isinstance(content, dict) else {"summary": str(content)}
            return ReflectionMemory(
                **common,
                content=ReflectionMemoryContent(
                    reasoning=reflection_payload.get("reasoning"),
                    improvement_suggestions=reflection_payload.get("improvement_suggestions", []),
                    failure_analysis=reflection_payload.get("failure_analysis"),
                    summary=reflection_payload.get("summary"),
                ),
            )
        if self.classify_type(event) == "semantic":
            return SemanticMemory(**common, content=content)
        if self.classify_type(event) == "task":
            return TaskMemory(**common, content=content)
        return EpisodicMemory(**common, content=content)

    def archive_after_days(self, scope: str) -> int:
        return int(self._config.get("retention", {}).get("archive_after_days", {}).get(scope, 30))

    @staticmethod
    def _infer_source(event_type: str | None) -> str:
        if event_type in {"tool_execution", "tool_failure"}:
            return "tool"
        if event_type == "user_feedback":
            return "user"
        return "system"

    @staticmethod
    def _infer_priority(event_type: str | None) -> str:
        if event_type == "tool_failure":
            return "high"
        if event_type in {"reflection", "classification"}:
            return "medium"
        return "low"

    def _rule_for(self, event: dict[str, Any]) -> dict[str, Any]:
        event_type = event.get("event_type", "")
        return dict(self._config.get("write_rules", {}).get(event_type, {}))
