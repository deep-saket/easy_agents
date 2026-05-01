"""File-backed storage for global and user key-event memories."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class CollectionMemoryRepository:
    collection_runtime_dir: Path
    memory_dir: Path = field(init=False)
    global_path: Path = field(init=False)
    user_path: Path = field(init=False)

    def __post_init__(self) -> None:
        self.memory_dir = self.collection_runtime_dir / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.global_path = self.memory_dir / "global_key_event_memory.json"
        self.user_path = self.memory_dir / "user_key_event_memory.json"
        if not self.global_path.exists():
            self._write_json(self.global_path, {"version": 1, "updated_at": _utc_now_iso(), "events": []})
        if not self.user_path.exists():
            self._write_json(self.user_path, {"version": 1, "updated_at": _utc_now_iso(), "users": {}})

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return default
        return json.loads(content)

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def upsert_global_event(self, event_type: str, signal: str) -> None:
        payload = self._read_json(self.global_path, {"version": 1, "updated_at": _utc_now_iso(), "events": []})
        events = list(payload.get("events", []))
        row = next((e for e in events if e.get("event_type") == event_type), None)
        if row is None:
            row = {
                "event_type": event_type,
                "count": 0,
                "last_seen": _utc_now_iso(),
                "sample_signals": [],
            }
            events.append(row)
        row["count"] = int(row.get("count", 0)) + 1
        row["last_seen"] = _utc_now_iso()
        signals = list(row.get("sample_signals", []))
        if signal and signal not in signals:
            signals.append(signal)
        row["sample_signals"] = signals[-5:]
        payload["events"] = events
        payload["updated_at"] = _utc_now_iso()
        self._write_json(self.global_path, payload)

    def upsert_user_memory(self, *, session_id: str, user_memory: dict[str, Any]) -> None:
        payload = self._read_json(self.user_path, {"version": 1, "updated_at": _utc_now_iso(), "users": {}})
        users = dict(payload.get("users", {}))
        users[session_id] = {
            **user_memory,
            "updated_at": _utc_now_iso(),
        }
        payload["users"] = users
        payload["updated_at"] = _utc_now_iso()
        self._write_json(self.user_path, payload)
