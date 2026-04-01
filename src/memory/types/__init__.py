"""Created: 2026-03-31

Purpose: Initializes the types package exports.
"""

from src.memory.types.episodic import EpisodicMemory
from src.memory.types.error import ErrorMemory, ErrorMemoryContent
from src.memory.types.procedural import ProceduralMemory
from src.memory.types.reflection import ReflectionMemory, ReflectionMemoryContent
from src.memory.types.semantic import SemanticMemory
from src.memory.types.task import TaskMemory
from src.memory.types.working import WorkingMemory
from typing import Any

from src.memory.models import MemoryItem


_TYPE_MAP = {
    "semantic": SemanticMemory,
    "episodic": EpisodicMemory,
    "error": ErrorMemory,
    "reflection": ReflectionMemory,
    "task": TaskMemory,
}


def parse_memory_item(payload: dict[str, Any] | str | MemoryItem) -> MemoryItem:
    if isinstance(payload, MemoryItem):
        return payload
    if isinstance(payload, str):
        import json

        data = json.loads(payload)
    else:
        data = payload
    memory_type = data.get("type", "episodic")
    model = _TYPE_MAP.get(memory_type, MemoryItem)
    return model.model_validate(data)

__all__ = [
    "EpisodicMemory",
    "ErrorMemory",
    "ErrorMemoryContent",
    "parse_memory_item",
    "ProceduralMemory",
    "ReflectionMemory",
    "ReflectionMemoryContent",
    "SemanticMemory",
    "TaskMemory",
    "WorkingMemory",
]
