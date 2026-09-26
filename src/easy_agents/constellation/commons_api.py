"""Created: 2026-09-26

Purpose: Exposes the local Commons runtime as a typed, loopback-safe API.

Every route in this module operates on the caller's local SQLite database.
No endpoint performs network I/O, sends a message, modifies an external
calendar, or resumes an approved effect automatically.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, TypeVar

from fastapi import APIRouter, HTTPException, Query

from easy_agents.constellation.commons_runtime import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalRecord,
    ArtifactCreate,
    ArtifactVersion,
    CalendarDecision,
    CalendarProposal,
    CalendarProposalCreate,
    ClaimAssessment,
    ClaimVerificationRequest,
    CommonsRuntime,
    KnowledgeHit,
    KnowledgeSource,
    KnowledgeSourceCreate,
    KnowledgeSummary,
    ScheduledReview,
    ScheduledReviewCreate,
    ScheduledReviewDecision,
    VaultActivationRequest,
    VaultDefinition,
    VaultId,
    VaultMemoryCreate,
    VaultMemoryEntry,
    VaultPurgeRequest,
)


ResultT = TypeVar("ResultT")


def _call(operation: Callable[[], ResultT]) -> ResultT:
    """Maps domain failures to stable HTTP errors without leaking internals."""

    try:
        return operation()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def create_commons_router(runtime: CommonsRuntime) -> APIRouter:
    """Builds the reusable management API for one Commons runtime instance."""

    router = APIRouter(prefix="/api/v2/commons", tags=["Commons"])

    @router.get("/summary")
    def summary() -> dict[str, Any]:
        """Returns persistence mode, executable features, and safe record counts."""

        return {
            "backend": runtime.backend,
            "capabilities": sorted(runtime.capabilities()),
            "counts": runtime.counts(),
            "external_effects": False,
        }

    @router.get("/vaults", response_model=list[VaultDefinition])
    def list_vaults() -> tuple[VaultDefinition, ...]:
        """Lists Vault boundaries and lifecycle state, never their contents."""

        return runtime.list_vaults()

    @router.patch("/vaults/{vault_id}", response_model=VaultDefinition)
    def set_vault_active(
        vault_id: VaultId, request: VaultActivationRequest
    ) -> VaultDefinition:
        """Activates or deactivates a Vault after explicit confirmation."""

        return _call(lambda: runtime.set_vault_active(vault_id, request))

    @router.post("/vaults/{vault_id}/memories", response_model=VaultMemoryEntry)
    def add_memory(
        vault_id: VaultId, request: VaultMemoryCreate
    ) -> VaultMemoryEntry:
        """Stores one typed memory in exactly one named Vault."""

        return _call(lambda: runtime.add_memory(vault_id, request))

    @router.get("/vaults/{vault_id}/memories", response_model=list[VaultMemoryEntry])
    def search_memory(
        vault_id: VaultId,
        query: str = Query(default="", max_length=4_000),
        limit: int = Query(default=20, ge=1, le=1_000),
    ) -> tuple[VaultMemoryEntry, ...]:
        """Searches one Vault; cross-Vault retrieval is intentionally absent."""

        return _call(lambda: runtime.search_memory(vault_id, query, limit=limit))

    @router.get("/vaults/{vault_id}/export")
    def export_vault(vault_id: VaultId) -> dict[str, Any]:
        """Returns a portable JSON representation for user-controlled backup."""

        return _call(lambda: runtime.export_vault(vault_id))

    @router.delete("/vaults/{vault_id}/memories/{memory_id}")
    def delete_memory(vault_id: VaultId, memory_id: str) -> dict[str, Any]:
        """Permanently deletes one explicitly addressed memory."""

        _call(lambda: runtime.delete_memory(vault_id, memory_id))
        return {"deleted": True, "vault_id": vault_id, "memory_id": memory_id}

    @router.post("/vaults/{vault_id}/purge")
    def purge_vault(
        vault_id: VaultId, request: VaultPurgeRequest
    ) -> dict[str, Any]:
        """Deletes all Vault memories only after exact textual confirmation."""

        deleted = _call(lambda: runtime.purge_vault(vault_id, request))
        return {"deleted": deleted, "vault_id": vault_id}

    @router.post("/artifacts", response_model=ArtifactVersion)
    def create_artifact(request: ArtifactCreate) -> ArtifactVersion:
        """Creates an artifact or the next immutable version of one."""

        return _call(lambda: runtime.create_artifact(request))

    @router.get("/artifacts", response_model=list[ArtifactVersion])
    def list_artifacts(
        include_deleted: bool = False,
    ) -> tuple[ArtifactVersion, ...]:
        """Lists artifact versions, excluding soft-deleted versions by default."""

        return runtime.list_artifacts(include_deleted=include_deleted)

    @router.get("/artifacts/{artifact_id}", response_model=ArtifactVersion)
    def get_artifact(
        artifact_id: str,
        version: int | None = Query(default=None, ge=1),
    ) -> ArtifactVersion:
        """Gets a requested version or the latest active version."""

        return _call(lambda: runtime.get_artifact(artifact_id, version))

    @router.delete("/artifacts/{artifact_id}")
    def delete_artifact(
        artifact_id: str,
        version: int | None = Query(default=None, ge=1),
    ) -> dict[str, Any]:
        """Soft-deletes one version or all active versions."""

        deleted = _call(lambda: runtime.delete_artifact(artifact_id, version))
        return {"artifact_id": artifact_id, "deleted_versions": deleted}

    @router.post("/knowledge/sources", response_model=KnowledgeSource)
    def add_knowledge_source(request: KnowledgeSourceCreate) -> KnowledgeSource:
        """Ingests explicitly supplied text as a content-addressed local source."""

        return _call(lambda: runtime.add_knowledge_source(request))

    @router.get("/knowledge/sources/{source_id}", response_model=KnowledgeSource)
    def get_knowledge_source(source_id: str) -> KnowledgeSource:
        """Gets one source by the stable identifier used in citations."""

        return _call(lambda: runtime.get_knowledge_source(source_id))

    @router.delete("/knowledge/sources/{source_id}")
    def delete_knowledge_source(source_id: str) -> dict[str, Any]:
        """Soft-deletes one source while preserving database audit history."""

        _call(lambda: runtime.delete_knowledge_source(source_id))
        return {"source_id": source_id, "deleted": True}

    @router.get("/knowledge/search", response_model=list[KnowledgeHit])
    def search_knowledge(
        query: str = Query(min_length=1, max_length=4_000),
        limit: int = Query(default=10, ge=1, le=100),
    ) -> tuple[KnowledgeHit, ...]:
        """Returns deterministic lexical hits with local citation identifiers."""

        return _call(lambda: runtime.search_knowledge(query, limit=limit))

    @router.get("/knowledge/summary", response_model=KnowledgeSummary)
    def summarize_knowledge(
        query: str = Query(min_length=1, max_length=4_000),
        limit: int = Query(default=5, ge=1, le=20),
    ) -> KnowledgeSummary:
        """Returns an extractive, citation-preserving local summary."""

        return _call(lambda: runtime.summarize_knowledge(query, limit=limit))

    @router.post("/knowledge/verify", response_model=list[ClaimAssessment])
    def verify_claims(
        request: ClaimVerificationRequest,
    ) -> tuple[ClaimAssessment, ...]:
        """Scores lexical source support; this is evidence triage, not proof."""

        return _call(lambda: runtime.verify_claims(request))

    @router.post("/reviews", response_model=ScheduledReview)
    def create_review(request: ScheduledReviewCreate) -> ScheduledReview:
        """Persists a one-time or recurring local review wakeup."""

        return _call(lambda: runtime.create_review(request))

    @router.get("/reviews", response_model=list[ScheduledReview])
    def list_reviews(
        status: Literal["scheduled", "due", "completed", "cancelled"] | None = None,
    ) -> tuple[ScheduledReview, ...]:
        """Lists reviews in due-time order."""

        return runtime.list_reviews(status=status)

    @router.post("/reviews/claim-due", response_model=list[ScheduledReview])
    def claim_due_reviews() -> tuple[ScheduledReview, ...]:
        """Immediately runs the same due transition used by the background monitor."""

        return runtime.claim_due_reviews()

    @router.post("/reviews/{review_id}/decision", response_model=ScheduledReview)
    def finish_review(
        review_id: str, request: ScheduledReviewDecision
    ) -> ScheduledReview:
        """Completes/cancels a review; completion advances recurring reviews."""

        return _call(
            lambda: runtime.finish_review(review_id, status=request.status)
        )

    @router.post("/approvals", response_model=ApprovalRecord)
    def create_approval(request: ApprovalCreate) -> ApprovalRecord:
        """Persists an approval and resumable context without running effects."""

        return _call(lambda: runtime.create_approval(request))

    @router.get("/approvals", response_model=list[ApprovalRecord])
    def list_approvals(
        status: Literal["pending", "approved", "rejected", "cancelled"] | None = None,
    ) -> tuple[ApprovalRecord, ...]:
        """Lists pending or historical local approval records."""

        return runtime.list_approvals(status=status)

    @router.post("/approvals/{approval_id}/decision", response_model=ApprovalRecord)
    def decide_approval(
        approval_id: str, request: ApprovalDecision
    ) -> ApprovalRecord:
        """Records one final human decision but does not execute the effect."""

        return _call(lambda: runtime.decide_approval(approval_id, request))

    @router.post("/calendar/proposals", response_model=CalendarProposal)
    def propose_calendar(request: CalendarProposalCreate) -> CalendarProposal:
        """Creates a local-only calendar proposal for later approval."""

        return _call(lambda: runtime.propose_calendar(request))

    @router.get("/calendar", response_model=list[CalendarProposal])
    def inspect_calendar(
        starts_after: datetime | None = None,
        ends_before: datetime | None = None,
        include_proposed: bool = True,
    ) -> tuple[CalendarProposal, ...]:
        """Inspects the local calendar projection without provider access."""

        return runtime.inspect_calendar(
            starts_after=starts_after,
            ends_before=ends_before,
            include_proposed=include_proposed,
        )

    @router.post("/calendar/{proposal_id}/decision", response_model=CalendarProposal)
    def decide_calendar(
        proposal_id: str, request: CalendarDecision
    ) -> CalendarProposal:
        """Approves/rejects locally and never writes an external calendar."""

        return _call(lambda: runtime.decide_calendar(proposal_id, request))

    return router


__all__ = ["create_commons_router"]
