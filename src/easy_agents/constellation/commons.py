"""Created: 2026-09-25

Purpose: Reports truthful implementation readiness for the shared Commons Circle.

The catalog describes desired topology.  This module separately records what
the local runtime can execute today, what is only partially implemented, what
is merely declared, and what is deliberately disabled at the Chat boundary.
Keeping these concepts separate prevents an ``active`` catalog label from
being mistaken for end-to-end functionality.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict

from easy_agents.galaxy.enums import EntityKind
from easy_agents.galaxy.registry import GalaxyRegistry


CommonsRuntimeStatus = Literal["operational", "partial", "declared", "disabled"]


class CommonsComponentReadiness(BaseModel):
    """One declared Commons component and its real runtime state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    display_name: str
    category: Literal["capability", "memory", "playbook", "policy", "satellite", "service"]
    catalog_status: Literal["active", "proposed"]
    runtime_status: CommonsRuntimeStatus
    evidence: tuple[str, ...]
    limitation: str | None = None


class CommonsRuntimeFoundation(BaseModel):
    """Cross-cutting dependencies used by every Commons component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gemma_ready: bool
    chat_history_backend: Literal["memory", "sqlite"]
    persistent_chat_history: bool
    response_provenance: bool = True
    generation_quality_checks: bool = True
    autonomous_external_effects: bool = False


class CommonsReadiness(BaseModel):
    """Auditable readiness report for the Commons Circle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    circle_id: Literal["commons"] = "commons"
    display_name: str = "Commons"
    purpose: str
    status: Literal["partial"] = "partial"
    summary: dict[CommonsRuntimeStatus, int]
    runtime: CommonsRuntimeFoundation
    components: tuple[CommonsComponentReadiness, ...]
    next_priorities: tuple[str, ...]


def build_commons_readiness(
    registry: GalaxyRegistry,
    *,
    executable_satellites: frozenset[str],
    gemma_ready: bool,
    chat_history_backend: Literal["memory", "sqlite"],
    runtime_capabilities: frozenset[str] = frozenset(),
) -> CommonsReadiness:
    """Builds a drift-checked Commons implementation report.

    Args:
        registry: Canonical Galaxy registry used by the running Control Room.
        executable_satellites: Satellites actually registered in Chat's local
            executor, not merely present in the catalog.
        gemma_ready: Whether the external local Rogue Star passed readiness.
        chat_history_backend: Active bounded conversation-history backend.
        runtime_capabilities: Components backed by the active local Commons
            runtime rather than only represented in the catalog.

    Raises:
        ValueError: If the catalog adds or removes a Commons component without
            updating this explicit implementation audit.
    """

    circle = registry.get_circle("commons")
    audit_by_id = {item.id: item for item in _COMMONS_COMPONENTS}
    declared_ids = {
        member.id
        for member in circle.members
        if member.kind != EntityKind.PLANET
    }
    if declared_ids != set(audit_by_id):
        missing = sorted(declared_ids - set(audit_by_id))
        stale = sorted(set(audit_by_id) - declared_ids)
        raise ValueError(
            "Commons readiness audit is out of sync with the Galaxy registry: "
            f"missing={missing}, stale={stale}."
        )

    components: list[CommonsComponentReadiness] = []
    for identifier in sorted(declared_ids):
        item = audit_by_id[identifier]
        if identifier in runtime_capabilities:
            item = item.model_copy(
                update={
                    "runtime_status": "operational",
                    "evidence": (
                        "Implemented by the active local Commons runtime and exposed through typed APIs.",
                    ),
                    "limitation": (
                        "Local state only; provider-backed external effects remain disabled."
                        if identifier in {"calendar.inspect", "calendar.propose", "outbound_approval"}
                        else None
                    ),
                }
            )
        elif item.category == "satellite":
            if identifier in executable_satellites:
                item = item.model_copy(
                    update={
                        "runtime_status": "operational",
                        "evidence": (
                            "Registered in the local SatelliteExecutor used by Wormhole Chat.",
                        ),
                        "limitation": None,
                    }
                )
            elif item.runtime_status == "operational":
                item = item.model_copy(
                    update={
                        "runtime_status": "disabled",
                        "evidence": (
                            "Declared in the catalog but absent from the active executor.",
                        ),
                        "limitation": "Not executable through the current Chat runtime.",
                    }
                )
        components.append(item)

    counts = Counter(item.runtime_status for item in components)
    summary: dict[CommonsRuntimeStatus, int] = {
        status: counts.get(status, 0)
        for status in ("operational", "partial", "declared", "disabled")
    }
    return CommonsReadiness(
        purpose=circle.purpose,
        summary=summary,
        runtime=CommonsRuntimeFoundation(
            gemma_ready=gemma_ready,
            chat_history_backend=chat_history_backend,
            persistent_chat_history=chat_history_backend == "sqlite",
        ),
        components=tuple(components),
        next_priorities=(
            "Add rubric-specific evaluators to Adversarial Review.",
            "Connect approved primary-source adapters to Research with Provenance.",
            "Add multi-Planet Chat teams to Route & Synthesize.",
            "Add external providers only behind account configuration and explicit approval.",
        ),
    )


def _component(
    identifier: str,
    display_name: str,
    category: Literal["capability", "memory", "playbook", "policy", "satellite", "service"],
    runtime_status: CommonsRuntimeStatus,
    evidence: str,
    *,
    catalog_status: Literal["active", "proposed"] = "active",
    limitation: str | None = None,
) -> CommonsComponentReadiness:
    """Creates one compact immutable audit entry."""

    return CommonsComponentReadiness(
        id=identifier,
        display_name=display_name,
        category=category,
        catalog_status=catalog_status,
        runtime_status=runtime_status,
        evidence=(evidence,),
        limitation=limitation,
    )


_COMMONS_COMPONENTS = (
    _component(
        "adversarial_review",
        "Adversarial Review",
        "playbook",
        "partial",
        "A reusable Playbook is compiled and traced.",
        limitation="No rubric-specific evaluator or evidence executor is wired.",
    ),
    _component(
        "artifact_store",
        "Artifact Store",
        "service",
        "declared",
        "The service exists in the topology only.",
        catalog_status="proposed",
        limitation="No versioned artifact persistence API exists.",
    ),
    _component(
        "calendar.inspect",
        "Inspect schedule",
        "capability",
        "declared",
        "The capability and Charter references exist.",
        limitation="No calendar provider or local calendar store is connected.",
    ),
    _component(
        "calendar.propose",
        "Propose schedule changes",
        "capability",
        "declared",
        "The capability and approval boundary exist.",
        limitation="No typed calendar proposal executor exists.",
    ),
    _component(
        "coordination.route",
        "Route a mission",
        "capability",
        "operational",
        "Wormhole routing returns explainable Circle and Planet candidates.",
    ),
    _component(
        "exploration",
        "Exploration Vault",
        "memory",
        "partial",
        "The isolated scope is enforced by Fleet policy.",
        catalog_status="proposed",
        limitation="Chat memory is not yet selectable by named Vault.",
    ),
    _component(
        "feature_architect",
        "Feature Architect",
        "service",
        "operational",
        "Feature intake returns reuse, compose, extend, or create decisions.",
    ),
    _component(
        "future_company",
        "Future Company Vault",
        "memory",
        "declared",
        "The dormant scope and policy boundary are modeled.",
        catalog_status="proposed",
        limitation="Activation and Venture Decision Gate persistence are not implemented.",
    ),
    _component(
        "knowledge.search",
        "Search knowledge",
        "capability",
        "partial",
        "Scoped durable memory search is executable.",
        limitation="There is no general document index or approved external-source connector.",
    ),
    _component(
        "knowledge.summarize",
        "Summarize material",
        "capability",
        "partial",
        "Mac Gemma can generate advisory summaries from supplied context.",
        limitation="Source ingestion and summary-grounding validation are missing.",
    ),
    _component(
        "knowledge.verify_claims",
        "Verify claims and citations",
        "capability",
        "partial",
        "The provenance Playbook and safety language are compiled.",
        limitation="No citation resolver or primary-source verifier executes today.",
    ),
    _component(
        "long_term",
        "Long-Term Memory",
        "memory",
        "operational",
        "Explicit Memory Write and Memory Search use durable typed local storage.",
    ),
    _component(
        "mission_runtime",
        "Mission Runtime",
        "service",
        "operational",
        "Fleet Missions, Work Orders, Playbooks, policies, and results execute locally.",
    ),
    _component(
        "observability.inspect",
        "Inspect system health",
        "capability",
        "operational",
        "Redacted SQLite events, projections, SSE, Live, and Replay are available.",
    ),
    _component(
        "offline_strict",
        "Strict Offline Boundary",
        "policy",
        "operational",
        "Fleet policy blocks undeclared external-network access.",
    ),
    _component(
        "outbound_approval",
        "Outbound Approval Gate",
        "policy",
        "partial",
        "External effects stop with a typed approval request and trace event.",
        limitation="Approvals cannot yet be durably approved and resumed.",
    ),
    _component(
        "personal",
        "Personal Vault",
        "memory",
        "partial",
        "The personal scope is declared and enforced by Fleet policy.",
        catalog_status="proposed",
        limitation="The Chat memory UI does not yet expose Vault selection or export.",
    ),
    _component(
        "policy.assess",
        "Assess policy and risk",
        "capability",
        "operational",
        "PolicyEngine returns allow, block, or approval before Planet execution.",
    ),
    _component(
        "research_with_provenance",
        "Research with Provenance",
        "playbook",
        "partial",
        "The bounded research workflow is compiled and traced.",
        limitation="Source gathering and citation preservation remain advisory.",
    ),
    _component(
        "route_and_synthesize",
        "Route & Synthesize",
        "playbook",
        "partial",
        "Fleet can route and combine multiple typed Planet results.",
        limitation="Wormhole Chat currently requests a one-Planet team.",
    ),
    _component(
        "scheduled_review",
        "Scheduled Review",
        "playbook",
        "partial",
        "The review workflow and due-state semantics are declared.",
        limitation="No durable scheduler wakes or cancels Missions.",
    ),
    _component(
        "working",
        "Working Memory",
        "memory",
        "operational",
        "Bounded conversation history persists in SQLite for the Control Room.",
    ),
    _component("calculate", "Calculate", "satellite", "operational", "Executable locally."),
    _component(
        "email_classifier",
        "Email Classifier",
        "satellite",
        "disabled",
        "A shared tool implementation exists.",
        limitation="Not registered in Wormhole Chat.",
    ),
    _component(
        "email_search",
        "Email Search",
        "satellite",
        "disabled",
        "A stored-email tool implementation exists.",
        limitation="Not registered in Wormhole Chat.",
    ),
    _component(
        "email_summary",
        "Email Summary",
        "satellite",
        "disabled",
        "A stored-email summarization tool implementation exists.",
        limitation="Not registered in Wormhole Chat.",
    ),
    _component(
        "gmail_fetch",
        "Gmail Fetch",
        "satellite",
        "disabled",
        "A provider-backed tool implementation exists.",
        limitation="No account is enabled in Chat and network access is denied.",
    ),
    _component(
        "memory_search", "Memory Search", "satellite", "operational", "Executable locally."
    ),
    _component(
        "memory_write", "Memory Write", "satellite", "operational", "Executable locally."
    ),
    _component("unit_convert", "Unit Convert", "satellite", "operational", "Executable locally."),
)


__all__ = [
    "CommonsComponentReadiness",
    "CommonsReadiness",
    "CommonsRuntimeFoundation",
    "build_commons_readiness",
]
