"""Created: 2026-04-01

Purpose: Exposes the DuckDB-backed MailMind repository through shared storage.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from src.interfaces.email import MessageRepository
from src.schemas.domain import (
    ApprovalItem,
    ApprovalStatus,
    ClassificationResult,
    EmailMessage,
    MessageBundle,
    NotificationAttempt,
    ReplyDraft,
    ToolExecutionLog,
)
from src.schemas.messages import ConversationMessage


def _row_dict(description: list[tuple[Any, ...]], row: tuple[Any, ...]) -> dict[str, Any]:
    return {column[0]: value for column, value in zip(description, row, strict=False)}


class DuckDBMessageRepository(MessageRepository):
    """Stores message, conversation, and tool-log data in DuckDB."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))

    def init_db(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id VARCHAR PRIMARY KEY,
                source_id VARCHAR UNIQUE NOT NULL,
                thread_id VARCHAR,
                from_name VARCHAR,
                from_email VARCHAR NOT NULL,
                recipients_json JSON NOT NULL,
                subject VARCHAR NOT NULL,
                body_text VARCHAR NOT NULL,
                body_html VARCHAR,
                received_at TIMESTAMP NOT NULL,
                labels_json JSON NOT NULL,
                raw_json JSON NOT NULL,
                process_status VARCHAR NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS classifications (
                message_id VARCHAR PRIMARY KEY,
                payload_json JSON NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                id VARCHAR PRIMARY KEY,
                message_id VARCHAR UNIQUE NOT NULL,
                payload_json JSON NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                id VARCHAR PRIMARY KEY,
                target_id VARCHAR NOT NULL,
                kind VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                reason VARCHAR NOT NULL,
                payload_json JSON NOT NULL,
                created_at TIMESTAMP NOT NULL,
                decided_at TIMESTAMP
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_attempts (
                id VARCHAR PRIMARY KEY,
                message_id VARCHAR NOT NULL,
                channel VARCHAR NOT NULL,
                destination VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                error VARCHAR,
                payload_json JSON NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processing_state (
                key VARCHAR PRIMARY KEY,
                value_json JSON NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_logs (
                id VARCHAR PRIMARY KEY,
                tool_name VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                input_payload_json JSON NOT NULL,
                output_payload_json JSON,
                error VARCHAR,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_state (
                session_id VARCHAR PRIMARY KEY,
                state_json JSON NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR NOT NULL,
                role VARCHAR NOT NULL,
                content VARCHAR NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_source_id ON messages(source_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_received_at ON messages(received_at)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_logs_created_at ON tool_logs(created_at)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_conversation_messages_session ON conversation_messages(session_id)")

    def has_message(self, source_id: str) -> bool:
        return self._fetchone("SELECT 1 AS found FROM messages WHERE source_id = ?", [source_id]) is not None

    def save_message(self, message: EmailMessage) -> EmailMessage:
        self._conn.execute("DELETE FROM messages WHERE id = ? OR source_id = ?", [message.id, message.source_id])
        self._conn.execute(
            """
            INSERT INTO messages (
                id, source_id, thread_id, from_name, from_email, recipients_json, subject,
                body_text, body_html, received_at, labels_json, raw_json, process_status, created_at
            ) VALUES (?, ?, ?, ?, ?, CAST(? AS JSON), ?, ?, ?, ?, CAST(? AS JSON), CAST(? AS JSON), ?, ?)
            """,
            [
                message.id,
                message.source_id,
                message.thread_id,
                message.from_name,
                message.from_email,
                json.dumps(message.to),
                message.subject,
                message.body_text,
                message.body_html,
                message.received_at,
                json.dumps(message.labels),
                json.dumps(message.raw),
                message.process_status.value,
                message.created_at,
            ],
        )
        return message

    def get_message(self, message_id: str) -> EmailMessage | None:
        row = self._fetchone("SELECT * FROM messages WHERE id = ?", [message_id])
        return self._row_to_message(row) if row else None

    def get_message_by_source_id(self, source_id: str) -> EmailMessage | None:
        row = self._fetchone("SELECT * FROM messages WHERE source_id = ?", [source_id])
        return self._row_to_message(row) if row else None

    def list_messages(self, *, search: str | None = None, only_important: bool = False) -> list[MessageBundle]:
        return self.search_messages(query=search, limit=1000, only_important=only_important)

    def search_messages(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sender: str | None = None,
        limit: int = 100,
        only_important: bool = False,
    ) -> list[MessageBundle]:
        sql = """
            SELECT m.*, c.payload_json AS classification_json, d.payload_json AS draft_json
            FROM messages m
            LEFT JOIN classifications c ON c.message_id = m.id
            LEFT JOIN drafts d ON d.message_id = m.id
        """
        params: list[Any] = []
        clauses: list[str] = []
        if query:
            clauses.append("(lower(m.subject) LIKE ? OR lower(m.body_text) LIKE ? OR lower(m.from_email) LIKE ?)")
            pattern = f"%{query.lower()}%"
            params.extend([pattern, pattern, pattern])
        if category:
            clauses.append("json_extract_string(c.payload_json, '$.category') = ?")
            params.append(category)
        if sender:
            sender_pattern = f"%{sender.lower()}%"
            clauses.append("(lower(m.from_email) LIKE ? OR lower(coalesce(m.from_name, '')) LIKE ?)")
            params.extend([sender_pattern, sender_pattern])
        if date_from:
            clauses.append("m.received_at >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("m.received_at <= ?")
            params.append(date_to)
        if only_important:
            clauses.append("CAST(json_extract(c.payload_json, '$.priority_score') AS DOUBLE) >= 0.75")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY m.received_at DESC LIMIT ?"
        params.append(limit)
        return [
            MessageBundle(
                message=self._row_to_message(row),
                classification=ClassificationResult.model_validate_json(row["classification_json"])
                if row.get("classification_json")
                else None,
                draft=ReplyDraft.model_validate_json(row["draft_json"]) if row.get("draft_json") else None,
            )
            for row in self._fetchall(sql, params)
        ]

    def save_classification(self, result: ClassificationResult) -> ClassificationResult:
        self._conn.execute("DELETE FROM classifications WHERE message_id = ?", [result.message_id])
        self._conn.execute(
            """
            INSERT INTO classifications (message_id, payload_json, created_at)
            VALUES (?, CAST(? AS JSON), ?)
            """,
            [result.message_id, result.model_dump_json(), result.created_at],
        )
        return result

    def get_latest_classification(self, message_id: str) -> ClassificationResult | None:
        row = self._fetchone("SELECT payload_json FROM classifications WHERE message_id = ?", [message_id])
        return ClassificationResult.model_validate_json(row["payload_json"]) if row else None

    def save_draft(self, draft: ReplyDraft) -> ReplyDraft:
        self._conn.execute("DELETE FROM drafts WHERE id = ? OR message_id = ?", [draft.id, draft.message_id])
        self._conn.execute(
            """
            INSERT INTO drafts (id, message_id, payload_json, created_at, updated_at)
            VALUES (?, ?, CAST(? AS JSON), ?, ?)
            """,
            [draft.id, draft.message_id, draft.model_dump_json(), draft.created_at, draft.updated_at],
        )
        return draft

    def list_drafts(self) -> list[ReplyDraft]:
        rows = self._fetchall("SELECT payload_json FROM drafts ORDER BY updated_at DESC")
        return [ReplyDraft.model_validate_json(row["payload_json"]) for row in rows]

    def create_approval(self, item: ApprovalItem) -> ApprovalItem:
        self._conn.execute("DELETE FROM approvals WHERE id = ?", [item.id])
        self._conn.execute(
            """
            INSERT INTO approvals (id, target_id, kind, status, reason, payload_json, created_at, decided_at)
            VALUES (?, ?, ?, ?, ?, CAST(? AS JSON), ?, ?)
            """,
            [
                item.id,
                item.target_id,
                item.kind.value,
                item.status.value,
                item.reason,
                item.model_dump_json(),
                item.created_at,
                item.decided_at,
            ],
        )
        return item

    def get_approval(self, approval_id: str) -> ApprovalItem | None:
        row = self._fetchone("SELECT payload_json FROM approvals WHERE id = ?", [approval_id])
        return ApprovalItem.model_validate_json(row["payload_json"]) if row else None

    def list_approvals(self, *, pending_only: bool = False) -> list[ApprovalItem]:
        sql = "SELECT payload_json FROM approvals"
        params: list[Any] = []
        if pending_only:
            sql += " WHERE status = ?"
            params.append(ApprovalStatus.PENDING.value)
        sql += " ORDER BY created_at DESC"
        return [ApprovalItem.model_validate_json(row["payload_json"]) for row in self._fetchall(sql, params)]

    def update_approval(self, item: ApprovalItem) -> ApprovalItem:
        self._conn.execute(
            """
            UPDATE approvals
            SET status = ?, reason = ?, payload_json = CAST(? AS JSON), decided_at = ?
            WHERE id = ?
            """,
            [item.status.value, item.reason, item.model_dump_json(), item.decided_at, item.id],
        )
        return item

    def save_notification_attempt(self, attempt: NotificationAttempt) -> NotificationAttempt:
        self._conn.execute("DELETE FROM notification_attempts WHERE id = ?", [attempt.id])
        self._conn.execute(
            """
            INSERT INTO notification_attempts
            (id, message_id, channel, destination, status, error, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CAST(? AS JSON), ?)
            """,
            [
                attempt.id,
                attempt.message_id,
                attempt.channel,
                attempt.destination,
                attempt.status.value,
                attempt.error,
                attempt.model_dump_json(),
                attempt.created_at,
            ],
        )
        return attempt

    def save_tool_log(self, log: ToolExecutionLog) -> ToolExecutionLog:
        self._conn.execute("DELETE FROM tool_logs WHERE id = ?", [log.id])
        self._conn.execute(
            """
            INSERT INTO tool_logs
            (id, tool_name, status, input_payload_json, output_payload_json, error, created_at)
            VALUES (?, ?, ?, CAST(? AS JSON), CAST(? AS JSON), ?, ?)
            """,
            [
                log.id,
                log.tool_name,
                log.status,
                json.dumps(log.input_payload),
                json.dumps(log.output_payload) if log.output_payload is not None else None,
                log.error,
                log.created_at,
            ],
        )
        return log

    def list_tool_logs(self, *, limit: int = 200, tool_name: str | None = None) -> list[ToolExecutionLog]:
        sql = """
            SELECT id, tool_name, status, input_payload_json, output_payload_json, error, created_at
            FROM tool_logs
        """
        params: list[Any] = []
        if tool_name:
            sql += " WHERE tool_name = ?"
            params.append(tool_name)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [
            ToolExecutionLog(
                id=row["id"],
                tool_name=row["tool_name"],
                status=row["status"],
                input_payload=json.loads(row["input_payload_json"]),
                output_payload=json.loads(row["output_payload_json"]) if row["output_payload_json"] else None,
                error=row["error"],
                created_at=row["created_at"],
            )
            for row in self._fetchall(sql, params)
        ]

    def set_processing_state(self, key: str, value: dict[str, str]) -> None:
        self._conn.execute("DELETE FROM processing_state WHERE key = ?", [key])
        self._conn.execute(
            """
            INSERT INTO processing_state (key, value_json, updated_at)
            VALUES (?, CAST(? AS JSON), NOW())
            """,
            [key, json.dumps(value)],
        )

    def get_processing_state(self, key: str) -> dict[str, str] | None:
        row = self._fetchone("SELECT value_json FROM processing_state WHERE key = ?", [key])
        return json.loads(row["value_json"]) if row else None

    def get_conversation_state(self, session_id: str) -> dict[str, object] | None:
        row = self._fetchone("SELECT state_json FROM conversation_state WHERE session_id = ?", [session_id])
        return json.loads(row["state_json"]) if row else None

    def save_conversation_state(self, session_id: str, state: dict[str, object]) -> None:
        self._conn.execute("DELETE FROM conversation_state WHERE session_id = ?", [session_id])
        self._conn.execute(
            """
            INSERT INTO conversation_state (session_id, state_json, updated_at)
            VALUES (?, CAST(? AS JSON), NOW())
            """,
            [session_id, json.dumps(state)],
        )

    def add_conversation_message(self, message: ConversationMessage) -> None:
        self._conn.execute("DELETE FROM conversation_messages WHERE id = ?", [message.id])
        self._conn.execute(
            """
            INSERT INTO conversation_messages (id, session_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [message.id, message.session_id, message.role, message.content, message.created_at],
        )

    def list_conversation_messages(self, session_id: str) -> list[ConversationMessage]:
        rows = self._fetchall(
            """
            SELECT id, session_id, role, content, created_at
            FROM conversation_messages
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [session_id, 100],
        )
        return list(
            reversed(
                [
                    ConversationMessage(
                        id=row["id"],
                        session_id=row["session_id"],
                        role=row["role"],
                        content=row["content"],
                        created_at=row["created_at"],
                    )
                    for row in rows
                ]
            )
        )

    def _fetchone(self, sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
        cursor = self._conn.execute(sql, params or [])
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_dict(cursor.description, row)

    def _fetchall(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        cursor = self._conn.execute(sql, params or [])
        return [_row_dict(cursor.description, row) for row in cursor.fetchall()]

    @staticmethod
    def _row_to_message(row: dict[str, Any]) -> EmailMessage:
        return EmailMessage(
            id=row["id"],
            source_id=row["source_id"],
            thread_id=row["thread_id"],
            from_name=row["from_name"],
            from_email=row["from_email"],
            to=json.loads(row["recipients_json"]),
            subject=row["subject"],
            body_text=row["body_text"],
            body_html=row["body_html"],
            received_at=row["received_at"],
            labels=json.loads(row["labels_json"]),
            raw=json.loads(row["raw_json"]),
            process_status=row["process_status"],
            created_at=row["created_at"],
        )


DuckDBStore = DuckDBMessageRepository

__all__ = ["DuckDBMessageRepository", "DuckDBStore"]
