"""Filler message selection for the conversation manager."""

from __future__ import annotations

import json
import threading
from pathlib import Path


class FillerManager:
    """Loads filler messages and returns non-repeating category messages."""

    def __init__(self, library_path: Path) -> None:
        payload = json.loads(library_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Filler library at {library_path} must be a JSON object.")
        self._library = {
            str(category): [str(item).strip() for item in messages if str(item).strip()]
            for category, messages in payload.items()
            if isinstance(messages, list)
        }
        self._indices: dict[str, int] = {category: 0 for category in self._library}
        self._lock = threading.Lock()

    def next_message(self, category: str) -> str:
        with self._lock:
            messages = self._library.get(category, [])
            if not messages:
                return ""
            index = self._indices.get(category, 0) % len(messages)
            self._indices[category] = index + 1
            return messages[index]
