"""Deny-by-default policy evaluation for Specialist Missions."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from easy_agents.fleet.models import (
    MissionRequest,
    PermissionGrant,
    PlaybookSpec,
    SpecialistManifest,
)
from easy_agents.fleet.registry import FleetRegistry


class PolicyDecision(BaseModel):
    """Auditable decision made before any model or capability call."""

    outcome: str
    effective_effects: list[str]
    memory_scope: str
    reasons: list[str] = Field(default_factory=list)
    approval_effects: list[str] = Field(default_factory=list)
    policy_ids: list[str] = Field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.outcome in {"allow", "approval"}


class PolicyEngine:
    """Applies Charter, memory, network, and human-approval boundaries."""

    def __init__(self, registry: FleetRegistry) -> None:
        self.registry = registry

    def evaluate(
        self,
        *,
        manifest: SpecialistManifest,
        request: MissionRequest,
        playbook: PlaybookSpec,
        parent_permissions: PermissionGrant | None = None,
    ) -> PolicyDecision:
        """Returns allow, approval, or block without executing an effect."""

        del playbook  # The first policy slice gates requested effects, not inert plan steps.
        inferred_effects = set() if request.advisory_only else infer_effects(request.objective)
        effects = sorted(set(request.requested_effects) | inferred_effects)
        approved = set(request.approved_effects)
        memory_scope = request.memory_scope or _default_scope(manifest)
        reasons: list[str] = []

        if memory_scope not in manifest.memory_scope_ids:
            return PolicyDecision(
                outcome="block",
                effective_effects=effects,
                memory_scope=memory_scope,
                reasons=[
                    f"Charter {manifest.id!r} cannot access memory scope {memory_scope!r}."
                ],
                policy_ids=manifest.policy_ids,
            )
        scope = self.registry.memory_scopes[memory_scope]
        if scope.dormant:
            return PolicyDecision(
                outcome="block",
                effective_effects=effects,
                memory_scope=memory_scope,
                reasons=[f"Memory scope {memory_scope!r} is dormant until a human activation Gate."],
                policy_ids=manifest.policy_ids,
            )

        if parent_permissions is not None:
            if memory_scope not in parent_permissions.memory_scopes:
                return PolicyDecision(
                    outcome="block",
                    effective_effects=effects,
                    memory_scope=memory_scope,
                    reasons=["Delegation cannot widen the parent Mission's memory scopes."],
                    policy_ids=manifest.policy_ids,
                )
            widened_effects = sorted(set(effects) - set(parent_permissions.effects))
            if widened_effects:
                return PolicyDecision(
                    outcome="block",
                    effective_effects=effects,
                    memory_scope=memory_scope,
                    reasons=[
                        "Delegation cannot add effects: " + ", ".join(widened_effects)
                    ],
                    policy_ids=manifest.policy_ids,
                )
            if request.allow_network and not parent_permissions.allow_network:
                return PolicyDecision(
                    outcome="block",
                    effective_effects=effects,
                    memory_scope=memory_scope,
                    reasons=["Delegation cannot enable network access denied to the parent Mission."],
                    policy_ids=manifest.policy_ids,
                )

        denied: set[str] = set()
        approvals: set[str] = set()
        objective = request.objective.lower()
        for policy_id in manifest.policy_ids:
            policy = self.registry.policies[policy_id]
            denied.update(set(effects) & set(policy.denied_effects))
            approvals.update(set(effects) & set(policy.approval_effects))
            unclassified = set(effects) - set(policy.allowed_effects) - set(policy.approval_effects)
            denied.update(unclassified)
            matched_terms = [term for term in policy.blocked_terms if term in objective]
            if matched_terms:
                reasons.append(
                    f"Policy {policy.display_name!r} blocked terms: {', '.join(matched_terms)}."
                )
            if request.allow_network:
                if policy.external_network == "deny":
                    denied.add("network")
                elif policy.external_network == "approval":
                    approvals.add("network")

        if reasons or denied:
            if denied:
                reasons.append("Denied effects: " + ", ".join(sorted(denied)) + ".")
            return PolicyDecision(
                outcome="block",
                effective_effects=effects,
                memory_scope=memory_scope,
                reasons=reasons,
                policy_ids=manifest.policy_ids,
            )

        pending = sorted(approvals - approved)
        if pending:
            return PolicyDecision(
                outcome="approval",
                effective_effects=effects,
                memory_scope=memory_scope,
                reasons=[
                    "Human approval is required before: " + ", ".join(pending) + "."
                ],
                approval_effects=pending,
                policy_ids=manifest.policy_ids,
            )

        return PolicyDecision(
            outcome="allow",
            effective_effects=effects,
            memory_scope=memory_scope,
            reasons=["Declared effects and memory scope satisfy the selected policy profiles."],
            policy_ids=manifest.policy_ids,
        )


_EFFECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("send", re.compile(r"\b(send|deliver|notify)\b", re.I)),
    ("call", re.compile(r"\b(call|phone)\b", re.I)),
    ("purchase", re.compile(r"\b(buy|purchase|checkout|order)\b", re.I)),
    ("payment", re.compile(r"\b(pay|payment|transfer money)\b", re.I)),
    ("publish", re.compile(r"\b(publish|post publicly|announce)\b", re.I)),
    ("submit", re.compile(r"\b(submit|file an application|apply for)\b", re.I)),
    ("delete", re.compile(r"\b(delete|erase|remove permanently)\b", re.I)),
    ("diagnose", re.compile(r"\b(diagnose|diagnosis)\b", re.I)),
    ("prescribe", re.compile(r"\b(prescribe|prescription)\b", re.I)),
    ("deploy", re.compile(r"\b(deploy to production|production deploy)\b", re.I)),
    ("hardware_control", re.compile(r"\b(transmit rf|command hardware|control hardware)\b", re.I)),
)


def infer_effects(objective: str) -> set[str]:
    """Conservatively infers effects that require central policy review."""

    return {effect for effect, pattern in _EFFECT_PATTERNS if pattern.search(objective)}


def _default_scope(manifest: SpecialistManifest) -> str:
    for preferred in ("employer_authorized", "personal", "exploration", "long_term", "working"):
        if preferred in manifest.memory_scope_ids:
            return preferred
    return manifest.memory_scope_ids[0]
