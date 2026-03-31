"""Created: 2026-03-31

Purpose: Implements the policies module for the shared memory platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from memory.models import MemoryItem
from memory.types import (
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
    """Classifies runtime events into concrete memory types and layers.

    This policy is the write-side decision point for long-term memory. It tells
    the rest of the system which events should become memories and which
    specific memory subtype should be created.
    """

    def should_store(self, event: dict[str, Any]) -> bool:
        """Determines whether an event should be persisted as memory.

        Args:
            event: A normalized event emitted by a tool, agent, or workflow.

        Returns:
            `True` when the event should be stored, otherwise `False`.
        """
        event_type = event.get("event_type")
        return event_type in {
            "tool_execution",
            "tool_failure",
            "classification",
            "summarization",
            "user_feedback",
            "reflection",
            "sleeping_task",
        }

    def classify_type(self, event: dict[str, Any]) -> str:
        """Maps an event to a memory taxonomy type."""
        event_type = event.get("event_type")
        if event_type == "tool_failure":
            return "error"
        if event_type == "reflection" or event_type == "summarization":
            return "reflection"
        if event_type == "classification":
            return "semantic"
        if event_type == "sleeping_task":
            return "task"
        return "episodic"

    def classify_layer(self, event: dict[str, Any]) -> str:
        """Maps an event to its initial storage layer."""
        memory_type = self.classify_type(event)
        if memory_type == "task":
            return "warm"
        if memory_type == "error":
            return "hot"
        return "warm"

    def build_item(self, event: dict[str, Any]) -> MemoryItem:
        """Builds a typed memory object from a normalized event.

        Args:
            event: A normalized event emitted by runtime code.

        Returns:
            A concrete typed memory instance such as `SemanticMemory` or
            `ErrorMemory`.
        """
        event_type = event.get("event_type")
        content = event.get("content", event)
        metadata = dict(event.get("metadata", {}))
        metadata.setdefault("event_type", event_type)
        metadata.setdefault("agent", event.get("agent", "unknown"))
        metadata.setdefault("tags", [])
        metadata.setdefault("source", self._infer_source(event_type))
        metadata.setdefault("priority", self._infer_priority(event_type))
        if event_type == "tool_failure":
            content = ErrorMemoryContent(
                input=event.get("input", {}),
                output=event.get("output"),
                error_type=event.get("error_type", "tool_failure"),
                correction=event.get("correction"),
                root_cause=event.get("root_cause", event.get("error")),
                agent=metadata["agent"],
            )
            return ErrorMemory(layer=self.classify_layer(event), content=content, metadata=metadata)
        if event_type in {"reflection", "summarization"}:
            if isinstance(content, dict):
                reflection_content = ReflectionMemoryContent(
                    reasoning=content.get("reasoning"),
                    improvement_suggestions=content.get("improvement_suggestions", []),
                    failure_analysis=content.get("failure_analysis"),
                    summary=content.get("summary"),
                )
            else:
                reflection_content = ReflectionMemoryContent(summary=str(content))
            return ReflectionMemory(layer=self.classify_layer(event), content=reflection_content, metadata=metadata)
        if event_type == "classification":
            return SemanticMemory(layer=self.classify_layer(event), content=content, metadata=metadata)
        if event_type == "sleeping_task":
            return TaskMemory(layer=self.classify_layer(event), content=content, metadata=metadata)
        return EpisodicMemory(layer=self.classify_layer(event), content=content, metadata=metadata)

    @staticmethod
    def _infer_source(event_type: str | None) -> str:
        """Infers the logical event source for memory metadata."""
        if event_type in {"tool_execution", "tool_failure"}:
            return "tool"
        if event_type == "user_feedback":
            return "user"
        return "system"

    @staticmethod
    def _infer_priority(event_type: str | None) -> str:
        """Infers a default memory priority from the event type."""
        if event_type == "tool_failure":
            return "high"
        if event_type in {"reflection", "classification"}:
            return "medium"
        return "low"
