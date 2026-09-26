"""Created: 2026-09-26

Purpose: Implements durable, local-first services shared by the Commons Circle.

The runtime owns state that should not be reimplemented by individual Planets:
named memory Vaults, versioned artifacts, local knowledge sources and citations,
scheduled reviews, approval decisions, and calendar proposals.  It deliberately
performs no network request or external effect.  Provider adapters may consume
approved records later, but this module remains deterministic and loopback-safe.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easy_agents.observability import EntityReference
from src.memory.models import MemoryRecord


VaultId = Literal[
    "working",
    "long_term",
    "personal",
    "employer_authorized",
    "exploration",
    "future_company",
]
VAULT_IDS: frozenset[str] = frozenset(
    {
        "working",
        "long_term",
        "personal",
        "employer_authorized",
        "exploration",
        "future_company",
    }
)


def parse_vault_id(value: object) -> VaultId:
    """Validates an untrusted value before using it as a named Vault boundary."""

    candidate = str(value)
    if candidate not in VAULT_IDS:
        raise ValueError(f"Unknown Vault: {candidate}")
    return cast(VaultId, candidate)


def _now() -> datetime:
    """Returns a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def _utc_iso(value: datetime) -> str:
    """Normalizes a timezone-aware timestamp for sortable SQLite storage."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(UTC).isoformat()


def _validate_payload_size(value: dict[str, Any], *, field_name: str) -> None:
    """Bounds flexible JSON payloads before they reach local persistence."""

    encoded = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    if len(encoded) > 64 * 1024:
        raise ValueError(f"{field_name} exceeds the 65536-byte limit")


def _identifier(prefix: str) -> str:
    """Creates a stable typed identifier."""

    return f"{prefix}-{uuid4().hex}"


class CommonsModel(BaseModel):
    """Strict immutable base contract for Commons API records."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class VaultDefinition(CommonsModel):
    """One named local data boundary and its activation state."""

    id: VaultId
    display_name: str
    sensitivity: Literal["temporary", "private", "confidential", "sensitive"]
    retention: str
    writable: bool = True
    active: bool = True


class VaultActivationRequest(CommonsModel):
    """Explicit confirmation required to change a Vault lifecycle."""

    active: bool
    confirmation: Literal["activate", "deactivate"]

    @model_validator(mode="after")
    def validate_confirmation(self) -> "VaultActivationRequest":
        expected = "activate" if self.active else "deactivate"
        if self.confirmation != expected:
            raise ValueError(f"confirmation must be {expected!r}")
        return self


class VaultPurgeRequest(CommonsModel):
    """Explicit destructive confirmation for removing every Vault memory."""

    confirmation: str

    def validate_for(self, vault_id: VaultId) -> None:
        """Rejects a purge unless the caller names the exact Vault."""

        expected = f"delete {vault_id}"
        if self.confirmation != expected:
            raise ValueError(f"confirmation must be {expected!r}")


class VaultMemoryCreate(CommonsModel):
    """Input for one explicit durable memory write."""

    content: str = Field(min_length=1, max_length=50_000)
    memory_type: Literal[
        "working", "episodic", "semantic", "error", "reflection", "task"
    ] = "semantic"
    tags: tuple[str, ...] = ()
    source_type: str = Field(default="user", min_length=1, max_length=100)
    source_id: str | None = Field(default=None, max_length=256)


class VaultMemoryEntry(CommonsModel):
    """One locally stored record inside a named Vault."""

    id: str
    vault_id: VaultId
    content: str
    memory_type: str
    tags: tuple[str, ...] = ()
    source_type: str
    source_id: str | None = None
    created_at: datetime
    updated_at: datetime

    def as_memory_record(self) -> MemoryRecord:
        """Adapts the record to the existing shared memory-tool contract."""

        return MemoryRecord(
            id=self.id,
            agent_id=f"galaxy_chat:{self.vault_id}",
            scope="agent_local",
            type=self.memory_type,
            layer="warm",
            content={"fact": self.content},
            content_text=self.content,
            source_type=self.source_type,
            source_id=self.source_id,
            tags=list(self.tags),
            metadata={
                "vault_id": self.vault_id,
                "agent_id": f"galaxy_chat:{self.vault_id}",
            },
        )


class ArtifactCreate(CommonsModel):
    """Input for a new immutable artifact version."""

    artifact_id: str | None = Field(default=None, max_length=160)
    name: str = Field(min_length=1, max_length=240)
    kind: str = Field(default="document", min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=1_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_metadata(self) -> "ArtifactCreate":
        _validate_payload_size(self.metadata, field_name="metadata")
        return self


class ArtifactVersion(CommonsModel):
    """One content-addressed version in the local Artifact Store."""

    artifact_id: str
    version: int = Field(ge=1)
    name: str
    kind: str
    content: str
    metadata: dict[str, Any]
    checksum_sha256: str
    created_at: datetime
    deleted_at: datetime | None = None


class KnowledgeSourceCreate(CommonsModel):
    """Input for one explicitly supplied local knowledge source."""

    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=1_000_000)
    source_uri: str | None = Field(default=None, max_length=2_000)
    tags: tuple[str, ...] = ()


class KnowledgeSource(CommonsModel):
    """One source whose identifier is used as a local citation."""

    id: str
    title: str
    content: str
    source_uri: str | None = None
    tags: tuple[str, ...] = ()
    checksum_sha256: str
    created_at: datetime


class KnowledgeHit(CommonsModel):
    """A lexical knowledge match with a stable citation identifier."""

    source_id: str
    title: str
    excerpt: str
    source_uri: str | None = None
    score: float = Field(ge=0)


class KnowledgeSummary(CommonsModel):
    """Deterministic extractive summary tied to local citations."""

    query: str
    summary: str
    citations: tuple[str, ...]
    source_count: int = Field(ge=0)


class ClaimAssessment(CommonsModel):
    """Explainable lexical support assessment for one supplied claim."""

    claim: str
    status: Literal["supported", "partial", "unsupported"]
    citations: tuple[str, ...]
    matched_terms: tuple[str, ...]
    coverage: float = Field(ge=0, le=1)


class ClaimVerificationRequest(CommonsModel):
    """Claims and optional source boundary for local verification."""

    claims: tuple[str, ...] = Field(min_length=1, max_length=50)
    source_ids: tuple[str, ...] = ()


class ScheduledReviewCreate(CommonsModel):
    """Input for a durable review wakeup."""

    title: str = Field(min_length=1, max_length=300)
    due_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    recurrence_days: int | None = Field(default=None, ge=1, le=3_650)

    @model_validator(mode="after")
    def validate_review(self) -> "ScheduledReviewCreate":
        _utc_iso(self.due_at)
        _validate_payload_size(self.payload, field_name="payload")
        return self


class ScheduledReview(CommonsModel):
    """One durable scheduled, due, completed, or cancelled review."""

    id: str
    title: str
    due_at: datetime
    payload: dict[str, Any]
    recurrence_days: int | None = None
    status: Literal["scheduled", "due", "completed", "cancelled"]
    created_at: datetime
    updated_at: datetime


class ScheduledReviewDecision(CommonsModel):
    """Explicit terminal action for a due or scheduled review."""

    status: Literal["completed", "cancelled"]


class ApprovalCreate(CommonsModel):
    """Input for a durable approval Gate record."""

    mission_id: str = Field(min_length=1, max_length=256)
    effects: tuple[str, ...] = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=4_000)
    resume_context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_resume_context(self) -> "ApprovalCreate":
        _validate_payload_size(self.resume_context, field_name="resume_context")
        return self


class ApprovalDecision(CommonsModel):
    """Explicit human decision; it does not execute the protected effect."""

    decision: Literal["approved", "rejected", "cancelled"]
    decided_by: str = Field(default="local_user", min_length=1, max_length=160)


class ApprovalRecord(CommonsModel):
    """Durable approval state and bounded continuation context."""

    id: str
    mission_id: str
    effects: tuple[str, ...]
    rationale: str
    resume_context: dict[str, Any]
    status: Literal["pending", "approved", "rejected", "cancelled"]
    decided_by: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class CalendarProposalCreate(CommonsModel):
    """Input for a local-only calendar change proposal."""

    title: str = Field(min_length=1, max_length=300)
    starts_at: datetime
    ends_at: datetime
    details: str = Field(default="", max_length=4_000)

    @model_validator(mode="after")
    def validate_window(self) -> "CalendarProposalCreate":
        _utc_iso(self.starts_at)
        _utc_iso(self.ends_at)
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class CalendarDecision(CommonsModel):
    """Local decision for a proposed calendar change."""

    decision: Literal["approved", "rejected", "cancelled"]


class CalendarProposal(CommonsModel):
    """One proposed or locally approved calendar item."""

    id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    details: str
    status: Literal["proposed", "approved", "rejected", "cancelled"]
    created_at: datetime
    decided_at: datetime | None = None


_VAULTS = (
    VaultDefinition(
        id="working",
        display_name="Working Memory",
        sensitivity="temporary",
        retention="bounded by conversation policy",
    ),
    VaultDefinition(
        id="long_term",
        display_name="Long-Term Memory",
        sensitivity="private",
        retention="user-controlled",
    ),
    VaultDefinition(
        id="personal",
        display_name="Personal Vault",
        sensitivity="private",
        retention="user-controlled",
    ),
    VaultDefinition(
        id="employer_authorized",
        display_name="Employer-Authorized Vault",
        sensitivity="confidential",
        retention="employment-boundary policy",
    ),
    VaultDefinition(
        id="exploration",
        display_name="Exploration Vault",
        sensitivity="private",
        retention="user-controlled",
    ),
    VaultDefinition(
        id="future_company",
        display_name="Future Company Vault",
        sensitivity="sensitive",
        retention="user-controlled after explicit activation",
        active=False,
    ),
)


class CommonsRuntime:
    """Thread-safe SQLite runtime for reusable local Commons services."""

    def __init__(
        self,
        *,
        db_path: Path | None = None,
        event_recorder: Any | None = None,
    ) -> None:
        """Creates an in-memory runtime or opens one durable local database."""

        if db_path is not None:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.event_recorder = event_recorder
        self._connection = sqlite3.connect(
            str(db_path) if db_path is not None else ":memory:",
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._initialize()

    @property
    def backend(self) -> Literal["memory", "sqlite"]:
        """Returns the active persistence mode."""

        return "sqlite" if self.db_path is not None else "memory"

    def _initialize(self) -> None:
        """Creates the local schema and inserts canonical Vault definitions."""

        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS commons_vaults (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    sensitivity TEXT NOT NULL,
                    retention TEXT NOT NULL,
                    writable INTEGER NOT NULL,
                    active INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commons_memories (
                    id TEXT PRIMARY KEY,
                    vault_id TEXT NOT NULL REFERENCES commons_vaults(id),
                    content TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_commons_memory_vault
                    ON commons_memories(vault_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS commons_artifacts (
                    artifact_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    checksum_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    deleted_at TEXT,
                    PRIMARY KEY (artifact_id, version)
                );
                CREATE TABLE IF NOT EXISTS commons_knowledge_sources (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_uri TEXT,
                    tags_json TEXT NOT NULL,
                    checksum_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    deleted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS commons_scheduled_reviews (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    recurrence_days INTEGER,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_commons_review_due
                    ON commons_scheduled_reviews(status, due_at);
                CREATE TABLE IF NOT EXISTS commons_approvals (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    effects_json TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    resume_context_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decided_by TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_commons_approval_mission
                    ON commons_approvals(mission_id, status);
                CREATE TABLE IF NOT EXISTS commons_calendar_proposals (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    starts_at TEXT NOT NULL,
                    ends_at TEXT NOT NULL,
                    details TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_commons_calendar_window
                    ON commons_calendar_proposals(starts_at, ends_at, status);
                """
            )
            for vault in _VAULTS:
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO commons_vaults (
                        id, display_name, sensitivity, retention, writable, active
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        vault.id,
                        vault.display_name,
                        vault.sensitivity,
                        vault.retention,
                        int(vault.writable),
                        int(vault.active),
                    ),
                )
            self._connection.commit()

    def capabilities(self) -> frozenset[str]:
        """Returns the executable Commons component identifiers."""

        return frozenset(
            {
                "artifact_store",
                "calendar.inspect",
                "calendar.propose",
                "exploration",
                "future_company",
                "knowledge.search",
                "knowledge.summarize",
                "knowledge.verify_claims",
                "outbound_approval",
                "personal",
                "scheduled_review",
            }
        )

    def counts(self) -> dict[str, int]:
        """Returns compact counts for the UI and readiness API."""

        with self._lock:
            tables = {
                "memories": "commons_memories",
                "artifacts": "commons_artifacts WHERE deleted_at IS NULL",
                "knowledge_sources": (
                    "commons_knowledge_sources WHERE deleted_at IS NULL"
                ),
                "scheduled_reviews": (
                    "commons_scheduled_reviews WHERE status IN ('scheduled', 'due')"
                ),
                "pending_approvals": "commons_approvals WHERE status = 'pending'",
                "calendar_items": (
                    "commons_calendar_proposals WHERE status IN ('proposed', 'approved')"
                ),
            }
            return {
                key: int(
                    self._connection.execute(
                        f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - fixed map only
                    ).fetchone()[0]
                )
                for key, table in tables.items()
            }

    def list_vaults(self) -> tuple[VaultDefinition, ...]:
        """Lists named Vaults without exposing their contents."""

        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM commons_vaults ORDER BY id"
            ).fetchall()
        return tuple(self._vault(row) for row in rows)

    def set_vault_active(
        self,
        vault_id: VaultId,
        request: VaultActivationRequest,
    ) -> VaultDefinition:
        """Activates or deactivates one Vault after explicit confirmation."""

        with self._lock:
            self._require_vault(vault_id)
            self._connection.execute(
                "UPDATE commons_vaults SET active = ? WHERE id = ?",
                (int(request.active), vault_id),
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT * FROM commons_vaults WHERE id = ?", (vault_id,)
            ).fetchone()
        self._record(
            "vault.lifecycle_changed",
            f"Vault {vault_id} {'activated' if request.active else 'deactivated'}",
            "active" if request.active else "inactive",
            {"vault_id": vault_id},
        )
        return self._vault(row)

    def add_memory(
        self,
        vault_id: VaultId,
        request: VaultMemoryCreate,
        *,
        memory_id: str | None = None,
        created_at: datetime | None = None,
    ) -> VaultMemoryEntry:
        """Writes one record to an active writable Vault."""

        now = created_at or _now()
        entry_id = memory_id or _identifier("memory")
        with self._lock:
            vault = self._require_vault(vault_id)
            if not vault.active:
                raise PermissionError(f"Vault {vault_id!r} is inactive.")
            if not vault.writable:
                raise PermissionError(f"Vault {vault_id!r} is read-only.")
            self._connection.execute(
                """
                INSERT OR REPLACE INTO commons_memories (
                    id, vault_id, content, memory_type, tags_json,
                    source_type, source_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    vault_id,
                    request.content,
                    request.memory_type,
                    json.dumps(request.tags),
                    request.source_type,
                    request.source_id,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            self._connection.commit()
        self._record(
            "vault.memory_written",
            f"Memory written to {vault_id}",
            "completed",
            {"vault_id": vault_id, "result_count": 1},
        )
        return self.get_memory(vault_id, entry_id)

    def get_memory(self, vault_id: VaultId, memory_id: str) -> VaultMemoryEntry:
        """Gets one record while enforcing its Vault boundary."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM commons_memories WHERE vault_id = ? AND id = ?",
                (vault_id, memory_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"Memory {memory_id!r} was not found in Vault {vault_id!r}.")
        return self._memory(row)

    def search_memory(
        self,
        vault_id: VaultId,
        query: str = "",
        *,
        limit: int = 20,
    ) -> tuple[VaultMemoryEntry, ...]:
        """Searches one named Vault and ranks non-adjacent query-term overlap."""

        self._require_limit(limit)
        with self._lock:
            self._require_vault(vault_id)
            params: list[Any] = [vault_id]
            sql = "SELECT * FROM commons_memories WHERE vault_id = ?"
            terms = _significant_terms(query)
            if terms:
                predicates = ["lower(content) LIKE ?" for _ in terms]
                sql += " AND (" + " OR ".join(predicates) + ")"
                params.extend(f"%{term}%" for term in terms)
                scores = [
                    "CASE WHEN lower(content) LIKE ? THEN 1 ELSE 0 END"
                    for _ in terms
                ]
                sql += " ORDER BY (" + " + ".join(scores) + ") DESC, created_at DESC"
                params.extend(f"%{term}%" for term in terms)
            else:
                sql += " ORDER BY created_at DESC"
            sql += " LIMIT ?"
            params.append(limit)
            rows = self._connection.execute(sql, params).fetchall()
        return tuple(self._memory(row) for row in rows)

    def export_vault(self, vault_id: VaultId) -> dict[str, Any]:
        """Returns a portable JSON-ready export without writing another file."""

        vault = next(item for item in self.list_vaults() if item.id == vault_id)
        entries = self.search_memory(vault_id, limit=10_000)
        return {
            "schema_version": 1,
            "exported_at": _now().isoformat(),
            "vault": vault.model_dump(mode="json"),
            "memories": [item.model_dump(mode="json") for item in entries],
        }

    def delete_memory(self, vault_id: VaultId, memory_id: str) -> None:
        """Permanently deletes one explicitly addressed memory record."""

        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM commons_memories WHERE vault_id = ? AND id = ?",
                (vault_id, memory_id),
            )
            self._connection.commit()
        if cursor.rowcount == 0:
            raise KeyError(f"Memory {memory_id!r} was not found in Vault {vault_id!r}.")
        self._record(
            "vault.memory_deleted",
            f"Memory deleted from {vault_id}",
            "completed",
            {"vault_id": vault_id, "result_count": 1},
        )

    def purge_vault(
        self, vault_id: VaultId, request: VaultPurgeRequest
    ) -> int:
        """Permanently deletes every memory after exact Vault confirmation."""

        request.validate_for(vault_id)
        with self._lock:
            self._require_vault(vault_id)
            cursor = self._connection.execute(
                "DELETE FROM commons_memories WHERE vault_id = ?", (vault_id,)
            )
            self._connection.commit()
        deleted = int(cursor.rowcount)
        self._record(
            "vault.purged",
            f"Vault {vault_id} purged",
            "completed",
            {"vault_id": vault_id, "result_count": deleted},
        )
        return deleted

    def create_artifact(self, request: ArtifactCreate) -> ArtifactVersion:
        """Creates the next immutable version for a local artifact."""

        artifact_id = request.artifact_id or _identifier("artifact")
        created_at = _now()
        checksum = hashlib.sha256(request.content.encode("utf-8")).hexdigest()
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM commons_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            version = int(row[0]) + 1
            self._connection.execute(
                """
                INSERT INTO commons_artifacts (
                    artifact_id, version, name, kind, content, metadata_json,
                    checksum_sha256, created_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    artifact_id,
                    version,
                    request.name,
                    request.kind,
                    request.content,
                    json.dumps(request.metadata, sort_keys=True, default=str),
                    checksum,
                    created_at.isoformat(),
                ),
            )
            self._connection.commit()
        self._record(
            "artifact.version_created",
            f"Artifact {artifact_id} version {version} created",
            "completed",
            {"artifact_id": artifact_id, "artifact_version": version},
        )
        return self.get_artifact(artifact_id, version)

    def get_artifact(
        self, artifact_id: str, version: int | None = None
    ) -> ArtifactVersion:
        """Gets one version, defaulting to the latest non-deleted version."""

        with self._lock:
            if version is None:
                row = self._connection.execute(
                    """
                    SELECT * FROM commons_artifacts
                    WHERE artifact_id = ? AND deleted_at IS NULL
                    ORDER BY version DESC LIMIT 1
                    """,
                    (artifact_id,),
                ).fetchone()
            else:
                row = self._connection.execute(
                    """
                    SELECT * FROM commons_artifacts
                    WHERE artifact_id = ? AND version = ?
                    """,
                    (artifact_id, version),
                ).fetchone()
        if row is None:
            raise KeyError(f"Artifact {artifact_id!r} was not found.")
        return self._artifact(row)

    def list_artifacts(self, *, include_deleted: bool = False) -> tuple[ArtifactVersion, ...]:
        """Lists all versions in stable newest-first order."""

        with self._lock:
            sql = "SELECT * FROM commons_artifacts"
            if not include_deleted:
                sql += " WHERE deleted_at IS NULL"
            sql += " ORDER BY created_at DESC, artifact_id, version DESC"
            rows = self._connection.execute(sql).fetchall()
        return tuple(self._artifact(row) for row in rows)

    def delete_artifact(self, artifact_id: str, version: int | None = None) -> int:
        """Soft-deletes one version or all versions for explicit recovery history."""

        deleted_at = _now().isoformat()
        with self._lock:
            if version is None:
                cursor = self._connection.execute(
                    """
                    UPDATE commons_artifacts SET deleted_at = ?
                    WHERE artifact_id = ? AND deleted_at IS NULL
                    """,
                    (deleted_at, artifact_id),
                )
            else:
                cursor = self._connection.execute(
                    """
                    UPDATE commons_artifacts SET deleted_at = ?
                    WHERE artifact_id = ? AND version = ? AND deleted_at IS NULL
                    """,
                    (deleted_at, artifact_id, version),
                )
            self._connection.commit()
        if cursor.rowcount == 0:
            raise KeyError(f"Artifact {artifact_id!r} was not found.")
        return int(cursor.rowcount)

    def add_knowledge_source(self, request: KnowledgeSourceCreate) -> KnowledgeSource:
        """Ingests one caller-supplied local source with a stable citation ID."""

        source_id = _identifier("source")
        created_at = _now()
        checksum = hashlib.sha256(request.content.encode("utf-8")).hexdigest()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO commons_knowledge_sources (
                    id, title, content, source_uri, tags_json,
                    checksum_sha256, created_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    source_id,
                    request.title,
                    request.content,
                    request.source_uri,
                    json.dumps(request.tags),
                    checksum,
                    created_at.isoformat(),
                ),
            )
            self._connection.commit()
        self._record(
            "knowledge.source_ingested",
            f"Knowledge source {source_id} ingested",
            "completed",
            {"source_id": source_id, "source_count": 1},
        )
        return self.get_knowledge_source(source_id)

    def get_knowledge_source(self, source_id: str) -> KnowledgeSource:
        """Gets one active local source by citation ID."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM commons_knowledge_sources
                WHERE id = ? AND deleted_at IS NULL
                """,
                (source_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Knowledge source {source_id!r} was not found.")
        return self._source(row)

    def delete_knowledge_source(self, source_id: str) -> None:
        """Soft-deletes a source so old citations remain auditable in SQLite."""

        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE commons_knowledge_sources SET deleted_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (_now().isoformat(), source_id),
            )
            self._connection.commit()
        if cursor.rowcount == 0:
            raise KeyError(f"Knowledge source {source_id!r} was not found.")

    def search_knowledge(self, query: str, *, limit: int = 10) -> tuple[KnowledgeHit, ...]:
        """Returns ranked lexical hits with stable local citations."""

        self._require_limit(limit)
        terms = _significant_terms(query)
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM commons_knowledge_sources
                WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 1000
                """
            ).fetchall()
        hits: list[KnowledgeHit] = []
        for row in rows:
            source = self._source(row)
            haystack = f"{source.title} {source.content}".lower()
            matched = [term for term in terms if term in haystack]
            if terms and not matched:
                continue
            score = float(len(matched) / max(1, len(terms)))
            hits.append(
                KnowledgeHit(
                    source_id=source.id,
                    title=source.title,
                    excerpt=_excerpt(source.content, terms),
                    source_uri=source.source_uri,
                    score=score,
                )
            )
        hits.sort(key=lambda item: (-item.score, item.title.lower(), item.source_id))
        return tuple(hits[:limit])

    def summarize_knowledge(self, query: str, *, limit: int = 5) -> KnowledgeSummary:
        """Builds a deterministic extractive summary that preserves citations."""

        hits = self.search_knowledge(query, limit=limit)
        lines = [f"[{hit.source_id}] {hit.excerpt}" for hit in hits]
        summary = "\n".join(lines) if lines else "No matching local knowledge source was found."
        return KnowledgeSummary(
            query=query,
            summary=summary,
            citations=tuple(hit.source_id for hit in hits),
            source_count=len(hits),
        )

    def verify_claims(
        self, request: ClaimVerificationRequest
    ) -> tuple[ClaimAssessment, ...]:
        """Assesses lexical support without claiming semantic proof."""

        if request.source_ids:
            sources = tuple(self.get_knowledge_source(item) for item in request.source_ids)
        else:
            with self._lock:
                rows = self._connection.execute(
                    """
                    SELECT * FROM commons_knowledge_sources
                    WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 1000
                    """
                ).fetchall()
            sources = tuple(self._source(row) for row in rows)
        assessments: list[ClaimAssessment] = []
        for claim in request.claims:
            terms = _significant_terms(claim)
            best_coverage = 0.0
            citations: list[str] = []
            matched_terms: set[str] = set()
            for source in sources:
                haystack = source.content.lower()
                matched = {term for term in terms if term in haystack}
                coverage = len(matched) / max(1, len(terms))
                if coverage > 0:
                    citations.append(source.id)
                    matched_terms.update(matched)
                best_coverage = max(best_coverage, coverage)
            if best_coverage >= 0.7:
                status = "supported"
            elif best_coverage >= 0.35:
                status = "partial"
            else:
                status = "unsupported"
            assessments.append(
                ClaimAssessment(
                    claim=claim,
                    status=status,
                    citations=tuple(citations[:10]),
                    matched_terms=tuple(sorted(matched_terms)),
                    coverage=round(best_coverage, 3),
                )
            )
        self._record(
            "knowledge.claims_verified",
            f"Assessed {len(assessments)} claim(s)",
            "completed",
            {
                "claim_count": len(assessments),
                "unsupported_count": sum(
                    item.status == "unsupported" for item in assessments
                ),
            },
        )
        return tuple(assessments)

    def create_review(self, request: ScheduledReviewCreate) -> ScheduledReview:
        """Schedules a durable review wakeup."""

        review_id = _identifier("review")
        now = _now()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO commons_scheduled_reviews (
                    id, title, due_at, payload_json, recurrence_days,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'scheduled', ?, ?)
                """,
                (
                    review_id,
                    request.title,
                    _utc_iso(request.due_at),
                    json.dumps(request.payload, sort_keys=True, default=str),
                    request.recurrence_days,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            self._connection.commit()
        return self.get_review(review_id)

    def get_review(self, review_id: str) -> ScheduledReview:
        """Gets one scheduled review."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM commons_scheduled_reviews WHERE id = ?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Scheduled review {review_id!r} was not found.")
        return self._review(row)

    def list_reviews(
        self, *, status: str | None = None
    ) -> tuple[ScheduledReview, ...]:
        """Lists reviews ordered by due time."""

        with self._lock:
            if status is None:
                rows = self._connection.execute(
                    "SELECT * FROM commons_scheduled_reviews ORDER BY due_at"
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT * FROM commons_scheduled_reviews
                    WHERE status = ? ORDER BY due_at
                    """,
                    (status,),
                ).fetchall()
        return tuple(self._review(row) for row in rows)

    def claim_due_reviews(self, *, now: datetime | None = None) -> tuple[ScheduledReview, ...]:
        """Atomically marks scheduled reviews due and returns new wakeups."""

        active_now = now or _now()
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id FROM commons_scheduled_reviews
                WHERE status = 'scheduled' AND due_at <= ? ORDER BY due_at
                """,
                (_utc_iso(active_now),),
            ).fetchall()
            identifiers = [str(row[0]) for row in rows]
            if identifiers:
                placeholders = ",".join("?" for _ in identifiers)
                self._connection.execute(
                    f"""
                    UPDATE commons_scheduled_reviews
                    SET status = 'due', updated_at = ?
                    WHERE id IN ({placeholders})
                    """,  # noqa: S608 - placeholder count only
                    [_utc_iso(active_now), *identifiers],
                )
                self._connection.commit()
            due = tuple(self.get_review(identifier) for identifier in identifiers)
        for review in due:
            self._record(
                "scheduled_review.due",
                f"Scheduled review due: {review.title}",
                "due",
                {"review_id": review.id},
            )
        return due

    def finish_review(
        self, review_id: str, *, status: Literal["completed", "cancelled"]
    ) -> ScheduledReview:
        """Completes or cancels a review and advances recurrence when configured."""

        review = self.get_review(review_id)
        if review.status in {"completed", "cancelled"}:
            raise ValueError(f"Scheduled review {review_id!r} is already {review.status}.")
        now = _now()
        with self._lock:
            if status == "completed" and review.recurrence_days:
                due_at = review.due_at + timedelta(days=review.recurrence_days)
                next_status = "scheduled"
            else:
                due_at = review.due_at
                next_status = status
            self._connection.execute(
                """
                UPDATE commons_scheduled_reviews
                SET status = ?, due_at = ?, updated_at = ? WHERE id = ?
                """,
                (next_status, due_at.isoformat(), now.isoformat(), review_id),
            )
            self._connection.commit()
        return self.get_review(review_id)

    def create_approval(self, request: ApprovalCreate) -> ApprovalRecord:
        """Creates a durable pending approval without executing any effect."""

        approval_id = _identifier("approval")
        now = _now()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO commons_approvals (
                    id, mission_id, effects_json, rationale, resume_context_json,
                    status, decided_by, created_at, decided_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, NULL)
                """,
                (
                    approval_id,
                    request.mission_id,
                    json.dumps(request.effects),
                    request.rationale,
                    json.dumps(request.resume_context, sort_keys=True, default=str),
                    now.isoformat(),
                ),
            )
            self._connection.commit()
        self._record(
            "approval.persisted",
            f"Approval {approval_id} persisted",
            "pending",
            {"approval_id": approval_id, "effect_count": len(request.effects)},
        )
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> ApprovalRecord:
        """Gets one durable approval including bounded resume context."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM commons_approvals WHERE id = ?", (approval_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Approval {approval_id!r} was not found.")
        return self._approval(row)

    def list_approvals(self, *, status: str | None = None) -> tuple[ApprovalRecord, ...]:
        """Lists approval records newest first."""

        with self._lock:
            if status is None:
                rows = self._connection.execute(
                    "SELECT * FROM commons_approvals ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT * FROM commons_approvals
                    WHERE status = ? ORDER BY created_at DESC
                    """,
                    (status,),
                ).fetchall()
        return tuple(self._approval(row) for row in rows)

    def decide_approval(
        self, approval_id: str, request: ApprovalDecision
    ) -> ApprovalRecord:
        """Records one final human decision exactly once."""

        decided_at = _now()
        with self._lock:
            current = self._connection.execute(
                "SELECT status FROM commons_approvals WHERE id = ?", (approval_id,)
            ).fetchone()
            if current is None:
                raise KeyError(f"Approval {approval_id!r} was not found.")
            if current["status"] != "pending":
                raise ValueError(
                    f"Approval {approval_id!r} is already {current['status']}."
                )
            cursor = self._connection.execute(
                """
                UPDATE commons_approvals
                SET status = ?, decided_by = ?, decided_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (
                    request.decision,
                    request.decided_by,
                    decided_at.isoformat(),
                    approval_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Approval {approval_id!r} was decided concurrently.")
            self._connection.commit()
        self._record(
            "approval.decided",
            f"Approval {approval_id} {request.decision}",
            request.decision,
            {"approval_id": approval_id},
        )
        return self.get_approval(approval_id)

    def propose_calendar(self, request: CalendarProposalCreate) -> CalendarProposal:
        """Creates a local proposal; it does not write to an external calendar."""

        proposal_id = _identifier("calendar")
        created_at = _now()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO commons_calendar_proposals (
                    id, title, starts_at, ends_at, details,
                    status, created_at, decided_at
                ) VALUES (?, ?, ?, ?, ?, 'proposed', ?, NULL)
                """,
                (
                    proposal_id,
                    request.title,
                    _utc_iso(request.starts_at),
                    _utc_iso(request.ends_at),
                    request.details,
                    created_at.isoformat(),
                ),
            )
            self._connection.commit()
        return self.get_calendar_proposal(proposal_id)

    def get_calendar_proposal(self, proposal_id: str) -> CalendarProposal:
        """Gets one local calendar proposal."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM commons_calendar_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Calendar proposal {proposal_id!r} was not found.")
        return self._calendar(row)

    def inspect_calendar(
        self,
        *,
        starts_after: datetime | None = None,
        ends_before: datetime | None = None,
        include_proposed: bool = True,
    ) -> tuple[CalendarProposal, ...]:
        """Lists approved local items and optionally pending proposals."""

        statuses = ("approved", "proposed") if include_proposed else ("approved",)
        placeholders = ",".join("?" for _ in statuses)
        params: list[Any] = list(statuses)
        sql = (
            "SELECT * FROM commons_calendar_proposals "
            f"WHERE status IN ({placeholders})"
        )
        if starts_after is not None:
            sql += " AND ends_at >= ?"
            params.append(_utc_iso(starts_after))
        if ends_before is not None:
            sql += " AND starts_at <= ?"
            params.append(_utc_iso(ends_before))
        sql += " ORDER BY starts_at"
        with self._lock:
            rows = self._connection.execute(sql, params).fetchall()
        return tuple(self._calendar(row) for row in rows)

    def decide_calendar(
        self, proposal_id: str, request: CalendarDecision
    ) -> CalendarProposal:
        """Approves, rejects, or cancels a local proposal without provider I/O."""

        with self._lock:
            current = self._connection.execute(
                "SELECT status FROM commons_calendar_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
            if current is None:
                raise KeyError(f"Calendar proposal {proposal_id!r} was not found.")
            if current["status"] != "proposed":
                raise ValueError(
                    f"Calendar proposal {proposal_id!r} is already {current['status']}."
                )
            cursor = self._connection.execute(
                """
                UPDATE commons_calendar_proposals
                SET status = ?, decided_at = ?
                WHERE id = ? AND status = 'proposed'
                """,
                (request.decision, _now().isoformat(), proposal_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    f"Calendar proposal {proposal_id!r} was decided concurrently."
                )
            self._connection.commit()
        return self.get_calendar_proposal(proposal_id)

    def close(self) -> None:
        """Closes the local database connection."""

        with self._lock:
            self._connection.close()

    def _require_vault(self, vault_id: VaultId) -> VaultDefinition:
        """Returns one Vault or raises a stable domain error."""

        row = self._connection.execute(
            "SELECT * FROM commons_vaults WHERE id = ?", (vault_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown Vault: {vault_id}")
        return self._vault(row)

    @staticmethod
    def _require_limit(limit: int) -> None:
        """Rejects unbounded list and search requests."""

        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")

    def _record(
        self,
        event_type: str,
        summary: str,
        status: str,
        attributes: dict[str, Any],
    ) -> None:
        """Emits safe operational metadata without exposing stored content."""

        if self.event_recorder is None:
            return
        try:
            self.event_recorder.record(
                event_type,
                summary=summary,
                status=status,
                actor=EntityReference(kind="service", id="commons_runtime"),
                attributes=attributes,
            )
        except Exception:
            return

    @staticmethod
    def _vault(row: sqlite3.Row) -> VaultDefinition:
        """Converts one SQLite row into a Vault contract."""

        return VaultDefinition(
            id=row["id"],
            display_name=row["display_name"],
            sensitivity=row["sensitivity"],
            retention=row["retention"],
            writable=bool(row["writable"]),
            active=bool(row["active"]),
        )

    @staticmethod
    def _memory(row: sqlite3.Row) -> VaultMemoryEntry:
        """Converts one SQLite row into a named-Vault memory entry."""

        return VaultMemoryEntry(
            id=row["id"],
            vault_id=row["vault_id"],
            content=row["content"],
            memory_type=row["memory_type"],
            tags=tuple(json.loads(row["tags_json"])),
            source_type=row["source_type"],
            source_id=row["source_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _artifact(row: sqlite3.Row) -> ArtifactVersion:
        """Converts one SQLite row into an immutable artifact version."""

        return ArtifactVersion(
            artifact_id=row["artifact_id"],
            version=int(row["version"]),
            name=row["name"],
            kind=row["kind"],
            content=row["content"],
            metadata=json.loads(row["metadata_json"]),
            checksum_sha256=row["checksum_sha256"],
            created_at=datetime.fromisoformat(row["created_at"]),
            deleted_at=(
                datetime.fromisoformat(row["deleted_at"])
                if row["deleted_at"]
                else None
            ),
        )

    @staticmethod
    def _source(row: sqlite3.Row) -> KnowledgeSource:
        """Converts one SQLite row into a local knowledge source."""

        return KnowledgeSource(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            source_uri=row["source_uri"],
            tags=tuple(json.loads(row["tags_json"])),
            checksum_sha256=row["checksum_sha256"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _review(row: sqlite3.Row) -> ScheduledReview:
        """Converts one SQLite row into a Scheduled Review."""

        return ScheduledReview(
            id=row["id"],
            title=row["title"],
            due_at=datetime.fromisoformat(row["due_at"]),
            payload=json.loads(row["payload_json"]),
            recurrence_days=row["recurrence_days"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _approval(row: sqlite3.Row) -> ApprovalRecord:
        """Converts one SQLite row into a durable approval record."""

        return ApprovalRecord(
            id=row["id"],
            mission_id=row["mission_id"],
            effects=tuple(json.loads(row["effects_json"])),
            rationale=row["rationale"],
            resume_context=json.loads(row["resume_context_json"]),
            status=row["status"],
            decided_by=row["decided_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            decided_at=(
                datetime.fromisoformat(row["decided_at"])
                if row["decided_at"]
                else None
            ),
        )

    @staticmethod
    def _calendar(row: sqlite3.Row) -> CalendarProposal:
        """Converts one SQLite row into a local calendar proposal."""

        return CalendarProposal(
            id=row["id"],
            title=row["title"],
            starts_at=datetime.fromisoformat(row["starts_at"]),
            ends_at=datetime.fromisoformat(row["ends_at"]),
            details=row["details"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            decided_at=(
                datetime.fromisoformat(row["decided_at"])
                if row["decided_at"]
                else None
            ),
        )


class CommonsVaultStoreAdapter:
    """Adapts named Commons Vaults to existing Memory tools."""

    def __init__(self, runtime: CommonsRuntime) -> None:
        """Binds existing memory-tool contracts to one Commons runtime."""

        self.runtime = runtime

    def add(self, item: MemoryRecord) -> MemoryRecord:
        """Stores a shared MemoryRecord in its declared or personal Vault."""

        raw_vault = item.metadata.get("vault_id", "personal")
        vault_id = parse_vault_id(raw_vault)
        created = self.runtime.add_memory(
            vault_id,
            VaultMemoryCreate(
                content=item.content_text or str(item.content),
                memory_type=item.type,
                tags=tuple(item.tags),
                source_type=item.source_type or "user",
                source_id=item.source_id,
            ),
            memory_id=item.id,
            created_at=item.created_at,
        )
        return created.as_memory_record()

    def search(
        self,
        query: str,
        filters: dict[str, object] | None = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        """Searches one explicitly selected Vault."""

        raw_vault = (filters or {}).get("vault_id", "personal")
        vault_id = parse_vault_id(raw_vault)
        return [
            item.as_memory_record()
            for item in self.runtime.search_memory(vault_id, query, limit=limit)
        ]

    def get(self, memory_id: str) -> MemoryRecord | None:
        """Searches all active Vaults for a compatibility lookup."""

        for vault in self.runtime.list_vaults():
            if not vault.active:
                continue
            try:
                return self.runtime.get_memory(vault.id, memory_id).as_memory_record()
            except KeyError:
                continue
        return None

    def delete(self, memory_id: str) -> None:
        """Deletes a compatibility record only after resolving its Vault."""

        for vault in self.runtime.list_vaults():
            try:
                self.runtime.delete_memory(vault.id, memory_id)
                return
            except KeyError:
                continue
        raise KeyError(f"Memory {memory_id!r} was not found.")


class CommonsMemoryRetriever:
    """Retriever adapter used by the existing Memory Search Satellite."""

    def __init__(self, store: CommonsVaultStoreAdapter) -> None:
        """Creates a retriever over the named-Vault compatibility adapter."""

        self.store = store

    def retrieve(
        self,
        query: str,
        filters: dict[str, object] | None = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        """Returns bounded records from one named Vault."""

        return self.store.search(query, filters=filters, limit=limit)


def _significant_terms(value: str) -> tuple[str, ...]:
    """Extracts stable lexical terms for local retrieval and evidence triage."""

    stop = {
        "about",
        "after",
        "before",
        "could",
        "from",
        "have",
        "into",
        "that",
        "their",
        "there",
        "these",
        "this",
        "were",
        "what",
        "when",
        "where",
        "which",
        "with",
        "would",
    }
    terms = {
        item
        for item in re.findall(r"[a-z0-9]+", value.lower())
        if len(item) >= 4 and item not in stop
    }
    return tuple(sorted(terms))


def _excerpt(content: str, terms: tuple[str, ...], *, limit: int = 360) -> str:
    """Returns a bounded excerpt centered near the earliest matching term."""

    normalized = " ".join(content.split())
    if len(normalized) <= limit:
        return normalized
    lowered = normalized.lower()
    offsets = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    start = max(0, (min(offsets) if offsets else 0) - 80)
    excerpt = normalized[start : start + limit].strip()
    return f"{'…' if start else ''}{excerpt}{'…' if start + limit < len(normalized) else ''}"


__all__ = [
    "ApprovalCreate",
    "ApprovalDecision",
    "ApprovalRecord",
    "ArtifactCreate",
    "ArtifactVersion",
    "CalendarDecision",
    "CalendarProposal",
    "CalendarProposalCreate",
    "ClaimAssessment",
    "ClaimVerificationRequest",
    "CommonsMemoryRetriever",
    "CommonsRuntime",
    "CommonsVaultStoreAdapter",
    "KnowledgeHit",
    "KnowledgeSource",
    "KnowledgeSourceCreate",
    "KnowledgeSummary",
    "ScheduledReview",
    "ScheduledReviewCreate",
    "ScheduledReviewDecision",
    "VaultActivationRequest",
    "VaultDefinition",
    "VaultId",
    "VaultMemoryCreate",
    "VaultMemoryEntry",
    "VaultPurgeRequest",
    "parse_vault_id",
]
