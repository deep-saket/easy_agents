from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from mailmind.core.interfaces import MessageRepository
from mailmind.core.models import (
    ApprovalItem,
    ApprovalStatus,
    ClassificationResult,
    EmailMessage,
    MessageBundle,
    NotificationAttempt,
    ReplyDraft,
)


class SQLiteMessageRepository(MessageRepository):
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL UNIQUE,
                    thread_id TEXT,
                    from_name TEXT,
                    from_email TEXT NOT NULL,
                    recipients_json TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body_text TEXT NOT NULL,
                    body_html TEXT,
                    received_at TEXT NOT NULL,
                    labels_json TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    process_status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS classifications (
                    message_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    target_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );
                CREATE TABLE IF NOT EXISTS notification_attempts (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS processing_state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def has_message(self, source_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM messages WHERE source_id = ?", (source_id,)).fetchone()
            return row is not None

    def save_message(self, message: EmailMessage) -> EmailMessage:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    id, source_id, thread_id, from_name, from_email, recipients_json, subject,
                    body_text, body_html, received_at, labels_json, raw_json, process_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    from_name = excluded.from_name,
                    from_email = excluded.from_email,
                    recipients_json = excluded.recipients_json,
                    subject = excluded.subject,
                    body_text = excluded.body_text,
                    body_html = excluded.body_html,
                    received_at = excluded.received_at,
                    labels_json = excluded.labels_json,
                    raw_json = excluded.raw_json,
                    process_status = excluded.process_status
                """,
                (
                    message.id,
                    message.source_id,
                    message.thread_id,
                    message.from_name,
                    message.from_email,
                    json.dumps(message.to),
                    message.subject,
                    message.body_text,
                    message.body_html,
                    message.received_at.isoformat(),
                    json.dumps(message.labels),
                    json.dumps(message.raw),
                    message.process_status.value,
                    message.created_at.isoformat(),
                ),
            )
        return message

    def get_message(self, message_id: str) -> EmailMessage | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        return self._row_to_message(row) if row else None

    def get_message_by_source_id(self, source_id: str) -> EmailMessage | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM messages WHERE source_id = ?", (source_id,)).fetchone()
        return self._row_to_message(row) if row else None

    def list_messages(self, *, search: str | None = None, only_important: bool = False) -> list[MessageBundle]:
        query = """
            SELECT m.*, c.payload_json AS classification_json, d.payload_json AS draft_json
            FROM messages m
            LEFT JOIN classifications c ON c.message_id = m.id
            LEFT JOIN drafts d ON d.message_id = m.id
        """
        params: list[object] = []
        clauses: list[str] = []
        if search:
            clauses.append("(lower(m.subject) LIKE ? OR lower(m.body_text) LIKE ? OR lower(m.from_email) LIKE ?)")
            pattern = f"%{search.lower()}%"
            params.extend([pattern, pattern, pattern])
        if only_important:
            clauses.append("json_extract(c.payload_json, '$.priority_score') >= 0.75")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY m.received_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        bundles: list[MessageBundle] = []
        for row in rows:
            message = self._row_to_message(row)
            classification = ClassificationResult.model_validate_json(row["classification_json"]) if row["classification_json"] else None
            draft = ReplyDraft.model_validate_json(row["draft_json"]) if row["draft_json"] else None
            bundles.append(MessageBundle(message=message, classification=classification, draft=draft))
        return bundles

    def save_classification(self, result: ClassificationResult) -> ClassificationResult:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO classifications (message_id, payload_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (result.message_id, result.model_dump_json(), result.created_at.isoformat()),
            )
        return result

    def get_latest_classification(self, message_id: str) -> ClassificationResult | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM classifications WHERE message_id = ?", (message_id,)
            ).fetchone()
        return ClassificationResult.model_validate_json(row["payload_json"]) if row else None

    def save_draft(self, draft: ReplyDraft) -> ReplyDraft:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO drafts (id, message_id, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    id = excluded.id,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    draft.id,
                    draft.message_id,
                    draft.model_dump_json(),
                    draft.created_at.isoformat(),
                    draft.updated_at.isoformat(),
                ),
            )
        return draft

    def list_drafts(self) -> list[ReplyDraft]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload_json FROM drafts ORDER BY updated_at DESC").fetchall()
        return [ReplyDraft.model_validate_json(row["payload_json"]) for row in rows]

    def create_approval(self, item: ApprovalItem) -> ApprovalItem:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO approvals (id, target_id, kind, status, reason, payload_json, created_at, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.target_id,
                    item.kind.value,
                    item.status.value,
                    item.reason,
                    item.model_dump_json(),
                    item.created_at.isoformat(),
                    item.decided_at.isoformat() if item.decided_at else None,
                ),
            )
        return item

    def get_approval(self, approval_id: str) -> ApprovalItem | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload_json FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return ApprovalItem.model_validate_json(row["payload_json"]) if row else None

    def list_approvals(self, *, pending_only: bool = False) -> list[ApprovalItem]:
        query = "SELECT payload_json FROM approvals"
        params: tuple[object, ...] = ()
        if pending_only:
            query += " WHERE status = ?"
            params = (ApprovalStatus.PENDING.value,)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [ApprovalItem.model_validate_json(row["payload_json"]) for row in rows]

    def update_approval(self, item: ApprovalItem) -> ApprovalItem:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE approvals
                SET status = ?, reason = ?, payload_json = ?, decided_at = ?
                WHERE id = ?
                """,
                (
                    item.status.value,
                    item.reason,
                    item.model_dump_json(),
                    item.decided_at.isoformat() if item.decided_at else None,
                    item.id,
                ),
            )
        return item

    def save_notification_attempt(self, attempt: NotificationAttempt) -> NotificationAttempt:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO notification_attempts
                (id, message_id, channel, destination, status, error, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.id,
                    attempt.message_id,
                    attempt.channel,
                    attempt.destination,
                    attempt.status.value,
                    attempt.error,
                    attempt.model_dump_json(),
                    attempt.created_at.isoformat(),
                ),
            )
        return attempt

    def set_processing_state(self, key: str, value: dict[str, str]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO processing_state (key, value_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, json.dumps(value)),
            )

    def get_processing_state(self, key: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value_json FROM processing_state WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value_json"]) if row else None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> EmailMessage:
        return EmailMessage.model_validate(
            {
                "id": row["id"],
                "source_id": row["source_id"],
                "thread_id": row["thread_id"],
                "from_name": row["from_name"],
                "from_email": row["from_email"],
                "to": json.loads(row["recipients_json"]),
                "subject": row["subject"],
                "body_text": row["body_text"],
                "body_html": row["body_html"],
                "received_at": row["received_at"],
                "labels": json.loads(row["labels_json"]),
                "raw": json.loads(row["raw_json"]),
                "process_status": row["process_status"],
                "created_at": row["created_at"],
            }
        )

