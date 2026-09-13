"""Explainable feature fit analysis for a personal agent constellation."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from easy_agents.constellation.directory import ConstellationDirectory
from easy_agents.constellation.models import (
    DirectoryMatch,
    DraftCharter,
    FeatureDecision,
    FeatureProposal,
    FeatureRequest,
    LifecycleStatus,
    RiskLevel,
)


_STOP_WORDS = {
    "a",
    "all",
    "an",
    "and",
    "can",
    "could",
    "for",
    "from",
    "help",
    "i",
    "in",
    "it",
    "me",
    "my",
    "of",
    "on",
    "please",
    "that",
    "the",
    "this",
    "to",
    "want",
    "with",
}

_SYNONYM_GROUPS = {
    "notification": {"alert", "notify", "notification", "remind", "reminder"},
    "calendar": {"appointment", "calendar", "deadline", "meeting", "schedule"},
    "paper": {"article", "literature", "paper", "publication"},
    "payment": {"buy", "pay", "payment", "purchase", "transfer"},
    "software": {"code", "coding", "develop", "engineering", "implement", "software"},
    "customer": {"customer", "lead", "prospect", "sales"},
    "utility": {"electricity", "gas", "utility", "water"},
    "research": {"experiment", "hypothesis", "research", "scientific", "study"},
    "travel": {"flight", "hotel", "irctc", "journey", "train", "travel", "trip"},
    "home": {"home", "household", "residence"},
    "machinelearning": {"machinelearning", "ml", "model", "training"},
    "market": {"market", "competitor", "competition"},
    "message": {"message", "email", "whatsapp", "communication"},
    "startup": {"startup", "business", "company", "venture"},
}

_PHRASE_ALIASES = {
    "machine learning": "machinelearning ml",
    "social media": "socialmedia publish",
    "customer discovery": "customer discovery market",
    "personal finance": "finance budget",
    "day to day": "routine",
    "due date": "deadline calendar",
    "research paper": "research paper literature",
}

_EFFECT_TERMS = {
    "delete": {"delete", "erase", "remove", "revoke"},
    "device_control": {"activate", "control", "lock", "switch", "unlock"},
    "payment": {"buy", "pay", "payment", "purchase", "transfer"},
    "send": {"deliver", "dispatch", "message", "notify", "post", "publish", "send", "whatsapp"},
    "shell": {"command", "deploy", "execute", "install", "shell"},
    "compute": {"benchmark", "evaluate", "run", "simulate"},
    "write": {"add", "book", "create", "record", "remind", "schedule", "track", "update"},
    "read": {"compare", "find", "read", "research", "search", "summarize"},
}

_HIGH_SENSITIVITY_TERMS = {
    "aadhaar",
    "account",
    "bank",
    "biometric",
    "credential",
    "health",
    "legal",
    "medical",
    "pan",
    "passport",
    "password",
    "tax",
}

_COMPOSITION_TERMS = {"and", "also", "after", "before", "then", "plus"}
_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MODERATE: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class FeatureIntakeService:
    """Decides whether a feature should reuse, compose, extend, or create.

    The initial implementation is deliberately deterministic and offline. It
    produces an auditable proposal; it does not generate executable code,
    grant permissions, or activate an agent.
    """

    def __init__(self, directory: ConstellationDirectory | None = None) -> None:
        self.directory = directory or ConstellationDirectory.default()

    def assess(self, request: str | FeatureRequest) -> FeatureProposal:
        """Analyzes one feature request against the configured directory."""

        normalized_request = (
            FeatureRequest(feature=request) if isinstance(request, str) else request
        )
        query_text = " ".join(
            part
            for part in (
                normalized_request.feature,
                normalized_request.desired_outcome or "",
                " ".join(normalized_request.constraints),
                " ".join(normalized_request.domain_hints),
            )
            if part
        )
        raw_tokens = self._raw_tokens(query_text)
        query_tokens = self._expanded_tokens(query_text)
        requested_effects = self._requested_effects(raw_tokens)

        guild_matches = self._match_guilds(query_tokens)
        capability_matches = self._match_capabilities(query_tokens, requested_effects)
        specialist_matches = self._match_specialists(query_tokens)

        decision = self._decide(
            raw_tokens=raw_tokens,
            requested_effects=requested_effects,
            specialist_matches=specialist_matches,
            capability_matches=capability_matches,
        )
        risk = self._infer_risk(raw_tokens, requested_effects, capability_matches)
        requires_approval = self._requires_approval(
            risk=risk,
            requested_effects=requested_effects,
            capability_matches=capability_matches,
        )
        inferred_guilds = [match.id for match in guild_matches[:3]]
        missing_capabilities = self._missing_capabilities(
            decision=decision,
            requested_effects=requested_effects,
            specialist_matches=specialist_matches,
            capability_matches=capability_matches,
        )
        draft_charter = None
        if decision is FeatureDecision.CREATE:
            draft_charter = self._draft_charter(
                normalized_request,
                inferred_guilds,
                missing_capabilities,
                risk,
            )

        confidence = self._confidence(decision, specialist_matches, capability_matches)
        rationale = self._rationale(
            decision,
            specialist_matches,
            capability_matches,
            requested_effects,
            requires_approval,
        )
        safe_to_auto_scaffold = (
            decision in {FeatureDecision.EXTEND, FeatureDecision.CREATE}
            and _RISK_ORDER[risk] <= _RISK_ORDER[RiskLevel.MODERATE]
            and not requires_approval
        )
        focused_capability_matches = self._focus_matches(
            capability_matches,
            ratio=0.4,
            minimum=0.25,
        )[:6]

        return FeatureProposal(
            proposal_id=self._proposal_id(normalized_request),
            request=normalized_request,
            decision=decision,
            confidence=confidence,
            inferred_guilds=inferred_guilds,
            requested_effects=sorted(requested_effects),
            risk=risk,
            network_required=self._network_required(focused_capability_matches),
            matched_specialists=self._focus_matches(
                specialist_matches,
                ratio=0.4 if decision is FeatureDecision.COMPOSE else 0.6,
                minimum=0.3,
            )[:6],
            matched_capabilities=focused_capability_matches,
            missing_capabilities=missing_capabilities,
            rationale=rationale,
            requires_human_approval=requires_approval,
            safe_to_auto_scaffold=safe_to_auto_scaffold,
            draft_charter=draft_charter,
            next_steps=self._next_steps(decision, requires_approval),
        )

    def _match_guilds(self, query_tokens: set[str]) -> list[DirectoryMatch]:
        entries = (
            (
                guild.id,
                guild.display_name,
                self._entry_terms(guild.id, guild.display_name, guild.purpose, guild.tags),
            )
            for guild in self.directory.guilds.values()
        )
        return self._rank(entries, query_tokens)

    def _match_capabilities(
        self,
        query_tokens: set[str],
        requested_effects: set[str],
    ) -> list[DirectoryMatch]:
        entries = (
            (
                capability.id,
                capability.display_name,
                self._entry_terms(
                    capability.id,
                    capability.display_name,
                    capability.description,
                    capability.tags,
                ),
            )
            for capability in self.directory.capabilities.values()
        )
        ranked = self._rank(entries, query_tokens)
        for match in ranked:
            capability = self.directory.capabilities[match.id]
            if requested_effects and requested_effects.issubset(set(capability.effects)):
                match.score = min(1.0, round(match.score + 0.12, 3))
        return sorted(ranked, key=lambda item: (-item.score, item.id))

    def _match_specialists(self, query_tokens: set[str]) -> list[DirectoryMatch]:
        entries: list[tuple[str, str, set[str]]] = []
        for specialist in self.directory.specialists.values():
            if specialist.status is not LifecycleStatus.ACTIVE:
                continue
            terms = self._entry_terms(
                specialist.id,
                specialist.display_name,
                specialist.purpose,
                specialist.tags,
            )
            for capability in self.directory.capabilities_for(specialist.id):
                terms.update(
                    self._entry_terms(
                        capability.id,
                        capability.display_name,
                        capability.description,
                        capability.tags,
                    )
                )
            entries.append((specialist.id, specialist.display_name, terms))
        return self._rank(entries, query_tokens)

    @staticmethod
    def _rank(
        entries: Iterable[tuple[str, str, set[str]]],
        query_tokens: set[str],
    ) -> list[DirectoryMatch]:
        matches: list[DirectoryMatch] = []
        denominator = max(2, min(8, len(query_tokens)))
        for identifier, display_name, terms in entries:
            overlap = sorted(query_tokens & terms)
            if not overlap:
                continue
            score = min(1.0, round((len(overlap) * 1.5) / denominator, 3))
            matches.append(
                DirectoryMatch(
                    id=identifier,
                    display_name=display_name,
                    score=score,
                    matched_terms=overlap,
                )
            )
        return sorted(matches, key=lambda item: (-item.score, item.id))

    @staticmethod
    def _focus_matches(
        matches: list[DirectoryMatch],
        *,
        ratio: float,
        minimum: float,
    ) -> list[DirectoryMatch]:
        if not matches:
            return []
        threshold = max(minimum, matches[0].score * ratio)
        return [match for match in matches if match.score >= threshold]

    def _decide(
        self,
        *,
        raw_tokens: set[str],
        requested_effects: set[str],
        specialist_matches: list[DirectoryMatch],
        capability_matches: list[DirectoryMatch],
    ) -> FeatureDecision:
        if not specialist_matches:
            return FeatureDecision.CREATE

        strong_specialists = [
            match
            for match in specialist_matches
            if len(match.matched_terms) >= 2 and match.score >= 0.3
        ]
        if raw_tokens & _COMPOSITION_TERMS and len(strong_specialists) >= 2:
            return FeatureDecision.COMPOSE

        best_specialist = specialist_matches[0]
        owned_capabilities = {
            item.id for item in self.directory.capabilities_for(best_specialist.id)
        }
        compatible_capabilities = [
            match
            for match in capability_matches
            if match.id in owned_capabilities
        ]
        covered_effects = {
            effect
            for match in compatible_capabilities
            for effect in self.directory.capabilities[match.id].effects
        }
        if (
            compatible_capabilities
            and compatible_capabilities[0].score >= 0.3
            and requested_effects.issubset(covered_effects)
        ):
            return FeatureDecision.REUSE
        return FeatureDecision.EXTEND

    def _infer_risk(
        self,
        raw_tokens: set[str],
        requested_effects: set[str],
        capability_matches: list[DirectoryMatch],
    ) -> RiskLevel:
        if "payment" in requested_effects:
            return RiskLevel.CRITICAL
        if requested_effects & {"delete", "device_control", "send", "shell"}:
            return RiskLevel.HIGH
        if raw_tokens & _HIGH_SENSITIVITY_TERMS:
            return RiskLevel.HIGH

        if capability_matches:
            return self.directory.capabilities[capability_matches[0].id].risk
        if "write" in requested_effects:
            return RiskLevel.MODERATE
        return RiskLevel.LOW

    def _requires_approval(
        self,
        *,
        risk: RiskLevel,
        requested_effects: set[str],
        capability_matches: list[DirectoryMatch],
    ) -> bool:
        if _RISK_ORDER[risk] >= _RISK_ORDER[RiskLevel.HIGH]:
            return True
        if requested_effects & {"delete", "device_control", "payment", "send", "shell"}:
            return True
        return bool(
            capability_matches
            and self.directory.capabilities[capability_matches[0].id].approval_required
        )

    def _network_required(self, capability_matches: list[DirectoryMatch]) -> bool:
        if not capability_matches:
            return False
        strongest_score = capability_matches[0].score
        relevant = [
            match
            for match in capability_matches
            if match.score >= strongest_score * 0.75
        ]
        return any(
            self.directory.capabilities[match.id].network_required
            for match in relevant
        )

    def _missing_capabilities(
        self,
        *,
        decision: FeatureDecision,
        requested_effects: set[str],
        specialist_matches: list[DirectoryMatch],
        capability_matches: list[DirectoryMatch],
    ) -> list[str]:
        if decision in {FeatureDecision.REUSE, FeatureDecision.COMPOSE}:
            return []
        prefix = specialist_matches[0].id if specialist_matches else "new_specialist"
        covered = {
            effect
            for match in capability_matches[:4]
            for effect in self.directory.capabilities[match.id].effects
        }
        missing_effects = sorted(requested_effects - covered)
        if missing_effects:
            return [f"{prefix}.{effect}" for effect in missing_effects]
        return [f"{prefix}.domain_workflow"]

    def _draft_charter(
        self,
        request: FeatureRequest,
        inferred_guilds: list[str],
        missing_capabilities: list[str],
        risk: RiskLevel,
    ) -> DraftCharter:
        identifier = self._slug(request.feature)
        guilds = inferred_guilds or ["commons"]
        return DraftCharter(
            id=f"{identifier}_specialist",
            display_name=f"{identifier.replace('_', ' ').title()} Specialist",
            mission=request.feature.strip(),
            guilds=guilds,
            proposed_capabilities=missing_capabilities,
            requested_permissions=[],
            risk=risk,
            status=LifecycleStatus.PROPOSED,
        )

    @staticmethod
    def _confidence(
        decision: FeatureDecision,
        specialist_matches: list[DirectoryMatch],
        capability_matches: list[DirectoryMatch],
    ) -> float:
        if decision is FeatureDecision.CREATE:
            strongest = specialist_matches[0].score if specialist_matches else 0.0
            return round(max(0.5, 1.0 - strongest), 3)
        scores = [match.score for match in specialist_matches[:2]]
        scores.extend(match.score for match in capability_matches[:2])
        return round(min(1.0, sum(scores) / max(1, len(scores)) + 0.1), 3)

    @staticmethod
    def _rationale(
        decision: FeatureDecision,
        specialist_matches: list[DirectoryMatch],
        capability_matches: list[DirectoryMatch],
        requested_effects: set[str],
        requires_approval: bool,
    ) -> list[str]:
        messages = {
            FeatureDecision.REUSE: (
                "An existing specialist already exposes a compatible capability."
            ),
            FeatureDecision.COMPOSE: (
                "The request spans multiple strong specialist matches and should "
                "become a playbook."
            ),
            FeatureDecision.EXTEND: (
                "An existing specialist is a domain fit, but its declared "
                "capabilities do not cover the request."
            ),
            FeatureDecision.CREATE: (
                "No directory specialist has enough domain overlap, so a draft "
                "charter is warranted."
            ),
        }
        rationale = [messages[decision]]
        if specialist_matches:
            rationale.append(
                "Strongest specialist match: "
                f"{specialist_matches[0].display_name} "
                f"({', '.join(specialist_matches[0].matched_terms)})."
            )
        if capability_matches:
            rationale.append(
                "Strongest capability match: "
                f"{capability_matches[0].display_name} "
                f"({', '.join(capability_matches[0].matched_terms)})."
            )
        if requested_effects:
            rationale.append(f"Requested effects: {', '.join(sorted(requested_effects))}.")
        if requires_approval:
            rationale.append(
                "Policy review is required before enabling the requested effects."
            )
        return rationale

    @staticmethod
    def _next_steps(
        decision: FeatureDecision,
        requires_approval: bool,
    ) -> list[str]:
        steps = {
            FeatureDecision.REUSE: [
                "Bind the feature to the matched capability and run its evals."
            ],
            FeatureDecision.COMPOSE: [
                "Generate a typed playbook joining the matched specialists."
            ],
            FeatureDecision.EXTEND: [
                "Draft the missing capability contract and add it to the matched "
                "specialist."
            ],
            FeatureDecision.CREATE: [
                "Review the draft charter, then scaffold it in an isolated "
                "workspace."
            ],
        }[decision]
        steps.append("Validate permissions, data scopes, budgets, and acceptance tests.")
        if requires_approval:
            steps.append(
                "Obtain explicit approval before activation or any external side "
                "effect."
            )
        else:
            steps.append(
                "Evaluate in the sandbox before promoting the change to active status."
            )
        return steps

    @classmethod
    def _entry_terms(cls, *parts: object) -> set[str]:
        return cls._expanded_tokens(" ".join(cls._flatten(parts)))

    @classmethod
    def _expanded_tokens(cls, value: str) -> set[str]:
        normalized = value.lower()
        for phrase, alias in _PHRASE_ALIASES.items():
            normalized = normalized.replace(phrase, alias)
        tokens = cls._raw_tokens(normalized) - _STOP_WORDS
        expanded = set(tokens)
        for canonical, group in _SYNONYM_GROUPS.items():
            if tokens & group:
                expanded.difference_update(group)
                expanded.add(canonical)
        return expanded

    @staticmethod
    def _raw_tokens(value: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", value.lower()))

    @staticmethod
    def _requested_effects(raw_tokens: set[str]) -> set[str]:
        effects = {
            effect
            for effect, terms in _EFFECT_TERMS.items()
            if raw_tokens & terms
        }
        if "train" in raw_tokens and raw_tokens & {
            "dataset",
            "learning",
            "machine",
            "ml",
            "model",
        }:
            effects.add("compute")
        return effects or {"read"}

    @staticmethod
    def _flatten(parts: Iterable[object]) -> Iterable[str]:
        for part in parts:
            if isinstance(part, str):
                yield part
            elif isinstance(part, Iterable):
                yield from (str(item) for item in part)
            else:
                yield str(part)

    @staticmethod
    def _slug(value: str) -> str:
        tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", value.lower())
            if token not in _STOP_WORDS
        ][:6]
        return "_".join(tokens) or "new"

    @staticmethod
    def _proposal_id(request: FeatureRequest) -> str:
        canonical = request.model_dump_json(exclude_none=True)
        return f"feature-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:12]}"
