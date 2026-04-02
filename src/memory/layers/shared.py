"""Created: 2026-03-31

Purpose: Implements the shared module for the shared memory platform layer.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from src.memory.models import MemoryRecord


def content_to_jsonable(content: Any) -> Any:
    if isinstance(content, BaseModel):
        return content.model_dump(mode="json")
    return content


def content_to_text(content: Any) -> str:
    content = content_to_jsonable(content)
    if isinstance(content, str):
        return content
    return json.dumps(content, sort_keys=True, ensure_ascii=True)


def filters_match(item: MemoryRecord, filters: dict[str, object] | None) -> bool:
    if not filters:
        return True
    for key, value in filters.items():
        if value is None:
            continue
        if key == "type" and item.type != value:
            return False
        if key == "memory_type" and item.type != value:
            return False
        if key == "layer" and item.layer != value:
            return False
        if key == "scope" and item.scope != value:
            return False
        if key in {"agent", "agent_id"} and item.agent_id != value:
            return False
        if key == "tags":
            expected_tags = value if isinstance(value, list) else [value]
            if not all(tag in item.tags for tag in expected_tags):
                return False
        if key == "metadata":
            expected = value if isinstance(value, dict) else {}
            for metadata_key, metadata_value in expected.items():
                if metadata_key == "tags":
                    item_tags = item.normalized_metadata().get("tags", [])
                    expected_tags = metadata_value if isinstance(metadata_value, list) else [metadata_value]
                    if not all(tag in item_tags for tag in expected_tags):
                        return False
                    continue
                if item.normalized_metadata().get(metadata_key) != metadata_value:
                    return False
        if key in {"source", "priority", "source_type", "source_id"} and item.normalized_metadata().get(key) != value:
            return False
    return True
