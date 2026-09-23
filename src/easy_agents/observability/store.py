"""SQLite event storage for local-first tracing and deterministic replay."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any

from easy_agents.observability.contracts import EventFilter, TraceEvent


class SQLiteEventStore:
    """Append-only event store with cursor queries and projection snapshots."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            isolation_level=None,
            timeout=10.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    @classmethod
    def memory(cls) -> "SQLiteEventStore":
        """Creates an isolated process-local store for tests and embedding."""

        return cls(":memory:")

    def _initialize(self) -> None:
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 10000")
            if self.path != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
                self._connection.execute("PRAGMA synchronous = NORMAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS trace_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT,
                    mission_id TEXT,
                    work_order_id TEXT,
                    run_id TEXT,
                    trace_id TEXT,
                    actor_kind TEXT,
                    actor_id TEXT,
                    subject_kind TEXT,
                    subject_id TEXT,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_trace_events_mission
                    ON trace_events(mission_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_trace_events_run
                    ON trace_events(run_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_trace_events_type
                    ON trace_events(event_type, sequence);
                CREATE INDEX IF NOT EXISTS idx_trace_events_actor
                    ON trace_events(actor_kind, actor_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_trace_events_subject
                    ON trace_events(subject_kind, subject_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_trace_events_status
                    ON trace_events(status, sequence);
                CREATE INDEX IF NOT EXISTS idx_trace_events_severity
                    ON trace_events(severity, sequence);

                CREATE TABLE IF NOT EXISTS projection_state (
                    projection_kind TEXT NOT NULL,
                    projection_key TEXT NOT NULL,
                    last_sequence INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (projection_kind, projection_key)
                );

                CREATE TABLE IF NOT EXISTS projection_metadata (
                    name TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            self._connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)"
            )

    def append(self, event: TraceEvent) -> tuple[TraceEvent, bool]:
        """Appends an event and returns ``(stored_event, was_inserted)``."""

        if event.sequence is not None:
            event = event.model_copy(update={"sequence": None})
        with self._lock:
            existing = self._connection.execute(
                "SELECT payload_json FROM trace_events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
            if existing is not None:
                return TraceEvent.model_validate_json(existing["payload_json"]), False

            actor = event.actor
            subject = event.subject
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._connection.execute(
                    """
                    INSERT INTO trace_events (
                        event_id, occurred_at, event_type, severity, status,
                        mission_id, work_order_id, run_id, trace_id,
                        actor_kind, actor_id, subject_kind, subject_id, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.occurred_at.isoformat(),
                        event.event_type,
                        event.severity.value,
                        event.status,
                        event.mission_id,
                        event.work_order_id,
                        event.run_id,
                        event.trace_id,
                        actor.kind if actor else None,
                        actor.id if actor else None,
                        subject.kind if subject else None,
                        subject.id if subject else None,
                        event.model_dump_json(),
                    ),
                )
                stored = event.model_copy(update={"sequence": int(cursor.lastrowid)})
                self._connection.execute(
                    "UPDATE trace_events SET payload_json = ? WHERE sequence = ?",
                    (stored.model_dump_json(), stored.sequence),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return stored, True

    def query(self, filters: EventFilter | None = None) -> list[TraceEvent]:
        """Returns ordered events matching a bounded cursor filter."""

        active = filters or EventFilter()
        clauses = ["sequence > ?"]
        params: list[Any] = [active.after_sequence]
        if active.before_sequence is not None:
            clauses.append("sequence < ?")
            params.append(active.before_sequence)
        for column, value in (
            ("mission_id", active.mission_id),
            ("run_id", active.run_id),
            ("event_type", active.event_type),
            ("status", active.status),
            ("severity", active.severity.value if active.severity else None),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if active.entity_kind is not None:
            clauses.append("(actor_kind = ? OR subject_kind = ?)")
            params.extend([active.entity_kind, active.entity_kind])
        if active.entity_id is not None:
            clauses.append("(actor_id = ? OR subject_id = ?)")
            params.extend([active.entity_id, active.entity_id])
        params.append(active.limit)
        sql = (
            "SELECT payload_json FROM trace_events WHERE "
            + " AND ".join(clauses)
            + " ORDER BY sequence ASC LIMIT ?"
        )
        with self._lock:
            rows = self._connection.execute(sql, params).fetchall()
        return [TraceEvent.model_validate_json(row["payload_json"]) for row in rows]

    def iter_all(self, *, page_size: int = 2_000) -> Iterator[TraceEvent]:
        """Iterates over all events without loading the full log at once."""

        cursor = 0
        while True:
            page = self.query(EventFilter(after_sequence=cursor, limit=page_size))
            if not page:
                return
            yield from page
            cursor = page[-1].sequence or cursor

    def latest_sequence(self) -> int:
        """Returns the most recently committed sequence, or zero."""

        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS value FROM trace_events"
            ).fetchone()
        return int(row["value"])

    def recent(self, *, limit: int = 100) -> list[TraceEvent]:
        """Returns the newest retained events in chronological order."""

        bounded = max(1, min(limit, 2_000))
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT payload_json FROM trace_events
                ORDER BY sequence DESC LIMIT ?
                """,
                (bounded,),
            ).fetchall()
        rows.reverse()
        return [TraceEvent.model_validate_json(row["payload_json"]) for row in rows]

    def count(self) -> int:
        """Returns the number of retained events."""

        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS value FROM trace_events"
            ).fetchone()
        return int(row["value"])

    def save_projections(
        self,
        records: Iterable[tuple[str, str, int, dict[str, Any]]],
        *,
        last_sequence: int,
        replace: bool = False,
    ) -> None:
        """Persists rebuildable projection records and their cursor."""

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                if replace:
                    self._connection.execute("DELETE FROM projection_state")
                self._connection.executemany(
                    """
                    INSERT INTO projection_state (
                        projection_kind, projection_key, last_sequence, payload_json
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(projection_kind, projection_key) DO UPDATE SET
                        last_sequence = excluded.last_sequence,
                        payload_json = excluded.payload_json
                    """,
                    [
                        (kind, key, sequence, json.dumps(payload, sort_keys=True))
                        for kind, key, sequence, payload in records
                    ],
                )
                self._connection.execute(
                    """
                    INSERT INTO projection_metadata(name, value)
                    VALUES ('last_sequence', ?)
                    ON CONFLICT(name) DO UPDATE SET value = excluded.value
                    """,
                    (str(last_sequence),),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def load_projections(self) -> tuple[int, list[tuple[str, str, dict[str, Any]]]]:
        """Loads projection records and their last applied event sequence."""

        with self._lock:
            meta = self._connection.execute(
                "SELECT value FROM projection_metadata WHERE name = 'last_sequence'"
            ).fetchone()
            rows = self._connection.execute(
                """
                SELECT projection_kind, projection_key, payload_json
                FROM projection_state
                ORDER BY projection_kind, projection_key
                """
            ).fetchall()
        last_sequence = int(meta["value"]) if meta is not None else 0
        records = [
            (row["projection_kind"], row["projection_key"], json.loads(row["payload_json"]))
            for row in rows
        ]
        return last_sequence, records

    def prune_before(self, sequence: int, *, batch_size: int = 1_000) -> int:
        """Deletes at most one bounded batch strictly before a sequence."""

        if sequence <= 1:
            return 0
        with self._lock:
            cursor = self._connection.execute(
                """
                DELETE FROM trace_events
                WHERE sequence IN (
                    SELECT sequence FROM trace_events
                    WHERE sequence < ? ORDER BY sequence LIMIT ?
                )
                """,
                (sequence, batch_size),
            )
        return max(cursor.rowcount, 0)

    def close(self) -> None:
        """Closes the underlying local database connection."""

        with self._lock:
            self._connection.close()
