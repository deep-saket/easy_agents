"""Local JSON datastore used by Connections Agent offline tools."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ConnectionsDataStore:
    """Provides typed helpers around JSON fixture and runtime files."""

    base_dir: Path
    data_dir: Path = field(init=False)
    runtime_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.data_dir = self.base_dir / "data"
        self.runtime_dir = self.base_dir / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_runtime_file("contact_attempts.json")
        self._ensure_runtime_file("verification_attempts.json")
        self._ensure_runtime_file("payment_links.json")
        self._ensure_runtime_file("promises.json")
        self._ensure_runtime_file("followups.json")
        self._ensure_runtime_file("dispositions.json")
        self._ensure_runtime_file("escalations.json")

    def _ensure_runtime_file(self, name: str) -> None:
        path = self.runtime_dir / name
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")

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

    def load_cases(self) -> list[dict[str, Any]]:
        return list(self._read_json(self.data_dir / "cases.json", []))

    def load_customers(self) -> list[dict[str, Any]]:
        return list(self._read_json(self.data_dir / "customers.json", []))

    def load_policies(self) -> list[dict[str, Any]]:
        return list(self._read_json(self.data_dir / "policies.json", []))

    def load_runtime(self, name: str) -> list[dict[str, Any]]:
        return list(self._read_json(self.runtime_dir / name, []))

    def save_runtime(self, name: str, rows: list[dict[str, Any]]) -> None:
        self._write_json(self.runtime_dir / name, rows)

    def append_runtime(self, name: str, row: dict[str, Any]) -> None:
        rows = self.load_runtime(name)
        rows.append(row)
        self.save_runtime(name, rows)

    def get_case(self, *, case_id: str | None = None, customer_id: str | None = None) -> dict[str, Any] | None:
        for row in self.load_cases():
            if case_id and row.get("case_id") == case_id:
                return row
            if customer_id and row.get("customer_id") == customer_id:
                return row
        return None

    def get_policy(self, loan_id: str) -> dict[str, Any] | None:
        for row in self.load_policies():
            if row.get("loan_id") == loan_id:
                return row
        return None

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        for row in self.load_customers():
            if row.get("customer_id") == customer_id:
                return row
        return None
