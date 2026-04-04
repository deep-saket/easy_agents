"""Created: 2026-04-01

Purpose: Implements the DuckDB-backed primary memory store.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import yaml

from src.memory.backends.base import MemoryBackend
from src.memory.models import MemoryRecord
from src.memory.types import parse_memory_item


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)


def _json_loads(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _row_dict(description: list[tuple[Any, ...]], row: tuple[Any, ...]) -> dict[str, Any]:
    return {column[0]: value for column, value in zip(description, row, strict=False)}


@dataclass(slots=True)
class DuckDBMemoryBackend(MemoryBackend):
    """Stores memory records in DuckDB.

    The backend can initialize its schema from either:

    - an injected YAML schema file
    - a built-in default schema

    This keeps the framework independent from repository-local config files.
    """

    db_path: Path
    schema_config_path: Path | None = None
    _conn: duckdb.DuckDBPyConnection = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self.db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        config = self._load_schema_config()
        tables = config.get("memory_tables", {})
        for table_name, table_config in tables.items():
            columns = table_config.get("columns", {})
            column_sql = ", ".join(f"{column_name} {column_type}" for column_name, column_type in columns.items())
            self._conn.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({column_sql})")
            for statement in table_config.get("indexes", []):
                self._conn.execute(statement)

    def _load_schema_config(self) -> dict[str, Any]:
        if self.schema_config_path is None:
            return {
                "memory_tables": {
                    "memory_records": {
                        "columns": {
                            "id": "VARCHAR PRIMARY KEY",
                            "agent_id": "VARCHAR",
                            "scope": "VARCHAR NOT NULL",
                            "memory_type": "VARCHAR NOT NULL",
                            "layer": "VARCHAR NOT NULL",
                            "content_text": "VARCHAR",
                            "content_json": "JSON",
                            "source_type": "VARCHAR",
                            "source_id": "VARCHAR",
                            "tags_json": "JSON",
                            "metadata_json": "JSON",
                            "importance": "DOUBLE",
                            "confidence": "DOUBLE",
                            "created_at": "TIMESTAMP NOT NULL",
                            "updated_at": "TIMESTAMP",
                            "archived_at": "TIMESTAMP",
                            "last_accessed_at": "TIMESTAMP",
                        },
                        "indexes": [
                            "CREATE INDEX IF NOT EXISTS idx_memory_records_created_at ON memory_records(created_at)",
                            "CREATE INDEX IF NOT EXISTS idx_memory_records_agent_scope ON memory_records(agent_id, scope)",
                            "CREATE INDEX IF NOT EXISTS idx_memory_records_type ON memory_records(memory_type)",
                            "CREATE INDEX IF NOT EXISTS idx_memory_records_layer ON memory_records(layer)",
                        ],
                    }
                }
            }
        return yaml.safe_load(self.schema_config_path.read_text(encoding="utf-8")) or {}

    def add_record(self, record: MemoryRecord) -> MemoryRecord:
        metadata = record.normalized_metadata()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO memory_records (
                id, agent_id, scope, memory_type, layer, content_text, content_json,
                source_type, source_id, tags_json, metadata_json, importance, confidence,
                created_at, updated_at, archived_at, last_accessed_at
            ) VALUES (?, ?, ?, ?, ?, ?, CAST(? AS JSON), ?, ?, CAST(? AS JSON), CAST(? AS JSON), ?, ?, ?, ?, ?, ?)
            """,
            [
                record.id,
                record.agent_id,
                record.scope,
                record.type,
                record.layer,
                record.content_text,
                _json_dumps(record.content_json),
                record.source_type,
                record.source_id,
                _json_dumps(record.tags),
                _json_dumps(metadata),
                record.importance,
                record.confidence,
                record.created_at,
                record.updated_at,
                record.archived_at,
                datetime.utcnow(),
            ],
        )
        return record.model_copy(update={"layer": "warm"})

    def get_record(self, record_id: str) -> MemoryRecord | None:
        cursor = self._conn.execute("SELECT * FROM memory_records WHERE id = ?", [record_id])
        description = cursor.description
        row = cursor.fetchone()
        if row is None:
            return None
        self._conn.execute("UPDATE memory_records SET last_accessed_at = NOW() WHERE id = ?", [record_id])
        return self._row_to_record(_row_dict(description, row))

    def query_records(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryRecord]:
        filters = filters or {}
        clauses: list[str] = []
        params: list[Any] = []
        if query.strip():
            clauses.append("lower(coalesce(content_text, '')) LIKE ?")
            params.append(f"%{query.lower()}%")
        scalar_fields = {
            "type": "memory_type",
            "memory_type": "memory_type",
            "layer": "layer",
            "scope": "scope",
            "agent_id": "agent_id",
            "source_type": "source_type",
            "source_id": "source_id",
        }
        for field_name, column_name in scalar_fields.items():
            value = filters.get(field_name)
            if value is not None:
                clauses.append(f"{column_name} = ?")
                params.append(value)
        if filters.get("agent") is not None:
            clauses.append("agent_id = ?")
            params.append(filters["agent"])
        tags = filters.get("tags")
        if isinstance(tags, str):
            tags = [tags]
        if isinstance(tags, list):
            for tag in tags:
                clauses.append("lower(coalesce(CAST(tags_json AS VARCHAR), '')) LIKE ?")
                params.append(f"%{str(tag).lower()}%")
        metadata_filters = filters.get("metadata")
        if isinstance(metadata_filters, dict):
            for key, value in metadata_filters.items():
                if key == "tags" and isinstance(value, list):
                    for tag in value:
                        clauses.append("lower(coalesce(CAST(tags_json AS VARCHAR), '')) LIKE ?")
                        params.append(f"%{str(tag).lower()}%")
                    continue
                if key in {"agent", "agent_id"}:
                    clauses.append("agent_id = ?")
                    params.append(value)
                    continue
                if key in {"scope", "memory_type", "type", "layer", "source_type", "source_id"}:
                    clauses.append(f"{'memory_type' if key == 'type' else key} = ?")
                    params.append(value)
                    continue
                clauses.append("lower(coalesce(CAST(metadata_json AS VARCHAR), '')) LIKE ?")
                params.append(f'%"{str(key).lower()}":%{str(value).lower()}%')
        sql = "SELECT * FROM memory_records"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cursor = self._conn.execute(sql, params)
        rows = cursor.fetchall()
        return [self._row_to_record(_row_dict(cursor.description, row)) for row in rows]

    def archive_records(self, *, scope: str | None = None, older_than_iso: str | None = None, limit: int = 500) -> list[MemoryRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if scope is not None:
            clauses.append("scope = ?")
            params.append(scope)
        if older_than_iso is not None:
            clauses.append("created_at < ?")
            params.append(older_than_iso)
        sql = "SELECT * FROM memory_records"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)
        cursor = self._conn.execute(sql, params)
        rows = cursor.fetchall()
        return [self._row_to_record(_row_dict(cursor.description, row)) for row in rows]

    def delete_record(self, record_id: str) -> None:
        self._conn.execute("DELETE FROM memory_records WHERE id = ?", [record_id])

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> MemoryRecord:
        return parse_memory_item(
            {
                "id": row["id"],
                "agent_id": row.get("agent_id"),
                "scope": row.get("scope", "agent_local"),
                "type": row.get("memory_type", "episodic"),
                "layer": row.get("layer", "warm"),
                "content": _json_loads(row.get("content_json")) if row.get("content_json") is not None else row.get("content_text"),
                "content_text": row.get("content_text"),
                "content_json": _json_loads(row.get("content_json")) if row.get("content_json") is not None else None,
                "source_type": row.get("source_type"),
                "source_id": row.get("source_id"),
                "tags": _json_loads(row.get("tags_json")) if row.get("tags_json") is not None else [],
                "metadata": _json_loads(row.get("metadata_json")) if row.get("metadata_json") is not None else {},
                "importance": row.get("importance"),
                "confidence": row.get("confidence"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "archived_at": row.get("archived_at"),
            }
        )
