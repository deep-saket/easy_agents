from __future__ import annotations

import json
from pathlib import Path

from mailmind.core.interfaces import AuditLogStore
from mailmind.core.models import DomainEvent


class JSONLAuditLogStore(AuditLogStore):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.touch(exist_ok=True)

    def append(self, event: DomainEvent) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")

    def read_recent(self, limit: int = 200) -> list[dict[str, object]]:
        lines = self._path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:] if line.strip()]

