"""Created: 2026-03-31

Purpose: Implements the warm module for the shared memory platform layer.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from memory.base import BaseMemoryLayer
from memory.layers.shared import content_to_jsonable, content_to_text, filters_match
from memory.models import MemoryItem
from memory.types import parse_memory_item


class WarmMemoryLayer(BaseMemoryLayer):
    """Stores indexed long-term memories in SQLite.

    Warm memory is the primary persistent query layer. It keeps structured JSON
    payloads, indexed metadata columns, and an FTS index for text retrieval.
    """

    def __init__(self, db_path: Path) -> None:
        """Initializes the warm layer and ensures its schema exists.

        Args:
            db_path: SQLite database path used for warm memory storage.
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Creates a SQLite connection configured for row access by name."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Creates the warm memory tables and indexes if they do not exist."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_text TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    source TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    tags_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_accessed_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_priority ON memories(priority)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_tags_text ON memories(tags_text)")
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(memory_id UNINDEXED, content_text)
                """
            )

    def add(self, item: MemoryItem) -> MemoryItem:
        """Writes a memory item into SQLite and updates its FTS entry."""
        stored = item.model_copy(update={"layer": "warm"})
        metadata = stored.normalized_metadata()
        content_json = json.dumps(content_to_jsonable(stored.content), sort_keys=True, ensure_ascii=True)
        metadata_json = json.dumps(metadata, sort_keys=True, ensure_ascii=True)
        content_text = content_to_text(stored.content)
        tags_text = " ".join(str(tag) for tag in metadata.get("tags", []))
        created_at = stored.created_at.isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, type, layer, content, content_text, metadata, agent, source, priority, tags_text, created_at, last_accessed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type=excluded.type,
                    layer=excluded.layer,
                    content=excluded.content,
                    content_text=excluded.content_text,
                    metadata=excluded.metadata,
                    agent=excluded.agent,
                    source=excluded.source,
                    priority=excluded.priority,
                    tags_text=excluded.tags_text,
                    created_at=excluded.created_at,
                    last_accessed_at=excluded.last_accessed_at
                """,
                (
                    stored.id,
                    stored.type,
                    stored.layer,
                    content_json,
                    content_text,
                    metadata_json,
                    metadata.get("agent", "unknown"),
                    metadata.get("source", "system"),
                    metadata.get("priority", "medium"),
                    tags_text,
                    created_at,
                    created_at,
                ),
            )
            conn.execute("DELETE FROM memories_fts WHERE memory_id = ?", (stored.id,))
            conn.execute("INSERT INTO memories_fts (memory_id, content_text) VALUES (?, ?)", (stored.id, content_text))
        return stored

    def get(self, memory_id: str) -> MemoryItem | None:
        """Fetches a memory item by identifier and records the access time."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE memories SET last_accessed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (memory_id,),
            )
        return self._row_to_item(row)

    def search(self, query: str, filters: dict[str, object] | None = None, limit: int = 20) -> list[MemoryItem]:
        """Searches warm memory using FTS plus structured metadata filters.

        Args:
            query: Free-text search query.
            filters: Optional structured filters such as type, agent, or tags.
            limit: Maximum number of results to return.

        Returns:
            Matching memory items from SQLite.
        """
        filters = filters or {}
        clauses = []
        params: list[object] = []
        joins = ""

        if query.strip():
            joins = "JOIN memories_fts ON memories.id = memories_fts.memory_id"
            clauses.append("memories_fts.content_text MATCH ?")
            params.append(query.strip())
        if filters.get("type"):
            clauses.append("memories.type = ?")
            params.append(filters["type"])
        if filters.get("layer"):
            clauses.append("memories.layer = ?")
            params.append(filters["layer"])
        if filters.get("agent"):
            clauses.append("memories.agent = ?")
            params.append(filters["agent"])
        if filters.get("source"):
            clauses.append("memories.source = ?")
            params.append(filters["source"])
        if filters.get("priority"):
            clauses.append("memories.priority = ?")
            params.append(filters["priority"])
        metadata_filters = filters.get("metadata")
        if isinstance(metadata_filters, dict):
            if metadata_filters.get("agent"):
                clauses.append("memories.agent = ?")
                params.append(metadata_filters["agent"])
            if metadata_filters.get("source"):
                clauses.append("memories.source = ?")
                params.append(metadata_filters["source"])
            if metadata_filters.get("priority"):
                clauses.append("memories.priority = ?")
                params.append(metadata_filters["priority"])
            if metadata_filters.get("tags"):
                tags = metadata_filters["tags"] if isinstance(metadata_filters["tags"], list) else [metadata_filters["tags"]]
                for tag in tags:
                    clauses.append("memories.tags_text LIKE ?")
                    params.append(f"%{tag}%")

        sql = "SELECT memories.* FROM memories "
        if joins:
            sql += joins + " "
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY memories.created_at DESC LIMIT ?"
        params.append(limit)

        try:
            with self._connect() as conn:
                rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            rows = []

        items = [self._row_to_item(row) for row in rows]
        if metadata_filters:
            items = [item for item in items if filters_match(item, {"metadata": metadata_filters})]
        if not query.strip():
            return items[:limit]
        if items:
            return items[:limit]

        fallback_sql = "SELECT * FROM memories WHERE content_text LIKE ? ORDER BY created_at DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(fallback_sql, (f"%{query.strip()}%", limit)).fetchall()
        items = [self._row_to_item(row) for row in rows]
        return [item for item in items if filters_match(item, filters)][:limit]

    def list_older_than(self, cutoff_iso: str, limit: int = 500) -> list[MemoryItem]:
        """Lists warm memories older than a cutoff timestamp."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE created_at < ? ORDER BY created_at ASC LIMIT ?",
                (cutoff_iso, limit),
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def delete(self, memory_id: str) -> None:
        """Deletes a memory item from SQLite and its FTS index."""
        with self._connect() as conn:
            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.execute("DELETE FROM memories_fts WHERE memory_id = ?", (memory_id,))

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> MemoryItem:
        """Converts a SQLite row back into a typed memory object."""
        return parse_memory_item(
            {
                "id": row["id"],
                "type": row["type"],
                "layer": row["layer"],
                "content": json.loads(row["content"]),
                "metadata": json.loads(row["metadata"]),
                "created_at": row["created_at"],
            }
        )
