"""Validated registries compiled from the Constellation knowledge graph."""

from __future__ import annotations

import re
from importlib import resources
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from easy_agents.constellation.directory import ConstellationDirectory
from easy_agents.constellation.knowledge_graph import (
    KnowledgeGraph,
    KnowledgeGraphOverlay,
    build_knowledge_graph,
    load_default_overlay,
)
from easy_agents.fleet.models import (
    MemoryScopeSpec,
    PlaybookSpec,
    PolicyProfile,
    RouteCandidate,
    SpecialistManifest,
    SpecialistStatus,
)


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "i",
    "in",
    "is",
    "me",
    "my",
    "of",
    "on",
    "please",
    "the",
    "to",
    "with",
}

_ROUTING_ALIASES: dict[str, tuple[str, ...]] = {
    "personal_steward": ("today", "daily", "priorities", "personal assistant", "chief of staff"),
    "schedule_coordinator": ("calendar", "appointment", "reminder", "deadline"),
    "household_operator": ("chores", "repair", "maintenance", "utilities"),
    "shopping_pantry_specialist": ("groceries", "pantry", "restock", "shopping list"),
    "family_relationships_specialist": ("mom", "mother", "dad", "father", "parents", "birthday"),
    "research_scientist": ("scientific exploration", "paper", "literature", "hypothesis"),
    "employment_boundary_guardian": ("employer", "employment", "nda", "confidential work"),
    "opportunity_portfolio_steward": ("opportunity", "portfolio", "thesis", "sector selection"),
    "idea_lab": ("brainstorm", "ideation", "invent", "startup ideas"),
    "energy_systems_scout": ("energy sector", "energy system", "power system"),
    "satcom_systems_architect": ("satcom", "satellite system", "space communication"),
    "clinical_problem_scout": ("unmet clinical need", "clinical problem"),
}


class FleetCatalog(BaseModel):
    """Packaged definitions shared by every dynamically compiled agent."""

    version: Literal[1] = 1
    memory_scopes: list[MemoryScopeSpec]
    policies: list[PolicyProfile]
    playbooks: list[PlaybookSpec]
    guild_defaults: dict[str, list[str]] = Field(default_factory=dict)
    guild_policies: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "FleetCatalog":
        scope_ids = _validate_unique("memory scope", [item.id for item in self.memory_scopes])
        policy_ids = _validate_unique("policy", [item.id for item in self.policies])
        _validate_unique("playbook", [item.id for item in self.playbooks])
        missing_scopes = sorted(
            {
                item
                for values in self.guild_defaults.values()
                for item in values
                if item not in scope_ids
            }
        )
        missing_policies = sorted(
            {
                item
                for values in self.guild_policies.values()
                for item in values
                if item not in policy_ids
            }
        )
        if missing_scopes:
            raise ValueError(
                "Guild defaults reference unknown memory scopes: "
                + ", ".join(missing_scopes)
            )
        if missing_policies:
            raise ValueError(
                "Guild defaults reference unknown policies: "
                + ", ".join(missing_policies)
            )
        return self


class FleetRegistry:
    """In-memory registry of Charters and their reusable dependencies."""

    def __init__(
        self,
        *,
        graph: KnowledgeGraph,
        catalog: FleetCatalog,
        specialists: list[SpecialistManifest],
    ) -> None:
        self.graph = graph
        self.catalog = catalog
        self.specialists = _as_unique_map("specialist", specialists)
        self.playbooks = _as_unique_map("playbook", catalog.playbooks)
        self.policies = _as_unique_map("policy", catalog.policies)
        self.memory_scopes = _as_unique_map("memory scope", catalog.memory_scopes)
        self._nodes = {node.id: node for node in graph.nodes}
        self._validate_manifests()

    @classmethod
    def default(cls) -> "FleetRegistry":
        """Compiles every current and planned Specialist into a Charter."""

        return cls.from_constellation(
            directory=ConstellationDirectory.default(),
            overlay=load_default_overlay(),
        )

    @classmethod
    def from_constellation(
        cls,
        *,
        directory: ConstellationDirectory,
        overlay: KnowledgeGraphOverlay | None = None,
    ) -> "FleetRegistry":
        """Compiles a validated directory and overlay into runtime manifests."""

        active_overlay = overlay or load_default_overlay()
        graph = build_knowledge_graph(directory, active_overlay)
        catalog = load_runtime_catalog()
        manifests = _compile_manifests(graph=graph, catalog=catalog)
        return cls(graph=graph, catalog=catalog, specialists=manifests)

    def list_specialists(
        self,
        *,
        status: SpecialistStatus | None = None,
    ) -> list[SpecialistManifest]:
        """Lists Charters in stable display-name order."""

        values = self.specialists.values()
        if status is not None:
            values = (item for item in values if item.status == status)
        return sorted(values, key=lambda item: (item.display_name.lower(), item.id))

    def get_specialist(self, specialist_id: str) -> SpecialistManifest:
        """Returns one compiled Charter or raises a descriptive error."""

        normalized = specialist_id.removeprefix("specialist:")
        try:
            return self.specialists[normalized]
        except KeyError as exc:
            raise KeyError(f"Unknown Specialist: {normalized}") from exc

    def get_playbook(self, playbook_id: str) -> PlaybookSpec:
        """Returns one reusable Playbook."""

        normalized = playbook_id.removeprefix("playbook:")
        try:
            return self.playbooks[normalized]
        except KeyError as exc:
            raise KeyError(f"Unknown Playbook: {normalized}") from exc

    def route(self, objective: str, *, limit: int = 5) -> list[RouteCandidate]:
        """Ranks relevant Specialists without instantiating any model process."""

        query_terms = _tokens(objective)
        candidates: list[RouteCandidate] = []
        for manifest in self.specialists.values():
            weighted_terms: dict[str, float] = {}
            for value in (manifest.display_name, manifest.id.replace("_", " ")):
                for token in _tokens(value):
                    weighted_terms[token] = max(weighted_terms.get(token, 0.0), 3.0)
            for token in _tokens(" ".join(_ROUTING_ALIASES.get(manifest.id, ()))):
                weighted_terms[token] = max(weighted_terms.get(token, 0.0), 3.2)
            for token in _tokens(" ".join(manifest.tags)):
                weighted_terms[token] = max(weighted_terms.get(token, 0.0), 2.5)
            for token in _tokens(manifest.purpose):
                weighted_terms[token] = max(weighted_terms.get(token, 0.0), 1.4)
            for capability_id in manifest.capability_ids:
                capability = self._nodes.get(f"capability:{capability_id}")
                if capability:
                    for token in _tokens(
                        " ".join([capability.label, capability.description, *capability.tags])
                    ):
                        weighted_terms[token] = max(weighted_terms.get(token, 0.0), 1.6)
            for playbook_id in manifest.playbook_ids:
                playbook = self.playbooks[playbook_id]
                for token in _tokens(
                    " ".join([playbook.display_name, playbook.description, *playbook.tags])
                ):
                    weighted_terms[token] = max(weighted_terms.get(token, 0.0), 1.7)
            for guild_id in manifest.guilds:
                guild = self._nodes.get(f"guild:{guild_id}")
                if guild:
                    for token in _tokens(" ".join([guild.label, *guild.tags])):
                        weighted_terms[token] = max(weighted_terms.get(token, 0.0), 1.1)
            matched = sorted(query_terms & set(weighted_terms))
            raw_score = sum(weighted_terms[token] for token in matched)
            phrase_bonus = 2.0 if manifest.display_name.lower() in objective.lower() else 0.0
            status_factor = 1.0 if manifest.status == SpecialistStatus.ACTIVE else 0.97
            score = min(1.0, ((raw_score + phrase_bonus) / max(len(query_terms) * 2.7, 4.0)) * status_factor)
            if score <= 0:
                continue
            candidates.append(
                RouteCandidate(
                    specialist_id=manifest.id,
                    display_name=manifest.display_name,
                    score=round(score, 4),
                    matched_terms=matched,
                    status=manifest.status,
                    guilds=manifest.guilds,
                )
            )
        candidates.sort(key=lambda item: (-item.score, item.display_name.lower(), item.specialist_id))
        if candidates:
            return candidates[: max(1, limit)]
        fallback = self.get_specialist("personal_steward")
        return [
            RouteCandidate(
                specialist_id=fallback.id,
                display_name=fallback.display_name,
                score=0.1,
                matched_terms=[],
                status=fallback.status,
                guilds=fallback.guilds,
            )
        ]

    def summary(self) -> dict[str, Any]:
        """Returns compact fleet counts for CLI, API, and UI clients."""

        active = sum(item.status == SpecialistStatus.ACTIVE for item in self.specialists.values())
        sandboxed = sum(item.status == SpecialistStatus.SANDBOXED for item in self.specialists.values())
        return {
            "specialists": len(self.specialists),
            "active": active,
            "sandboxed": sandboxed,
            "playbooks": len(self.playbooks),
            "policies": len(self.policies),
            "memory_scopes": len(self.memory_scopes),
        }

    def _validate_manifests(self) -> None:
        packaged_components = load_default_overlay().components
        tool_ids = {
            node.id.removeprefix("tool:")
            for node in self.graph.nodes
            if node.kind == "tool"
        } | {item.id for item in packaged_components if item.kind == "tool"}
        capability_ids = {
            node.id.removeprefix("capability:")
            for node in self.graph.nodes
            if node.kind == "capability"
        }
        model_ids = {
            node.id.removeprefix("model:")
            for node in self.graph.nodes
            if node.kind == "model" or node.metadata.get("resource_kind") == "model"
        } | {item.id for item in packaged_components if item.kind == "model"}
        for manifest in self.specialists.values():
            references = {
                "playbooks": set(manifest.playbook_ids) - set(self.playbooks),
                "policies": set(manifest.policy_ids) - set(self.policies),
                "memory scopes": set(manifest.memory_scope_ids) - set(self.memory_scopes),
                "capabilities": set(manifest.capability_ids) - capability_ids,
                "tools": set(manifest.tool_ids) - tool_ids,
                "models": set(manifest.model_ids) - model_ids,
            }
            for kind, missing in references.items():
                if missing:
                    raise ValueError(
                        f"Specialist {manifest.id!r} references unknown {kind}: "
                        + ", ".join(sorted(missing))
                    )


def load_runtime_catalog() -> FleetCatalog:
    """Loads reusable Playbook, policy, and memory definitions."""

    text = (
        resources.files("easy_agents.fleet")
        .joinpath("runtime_catalog.yaml")
        .read_text(encoding="utf-8")
    )
    payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError("Fleet runtime catalog must be a YAML mapping.")
    return FleetCatalog.model_validate(payload)


def _compile_manifests(
    *,
    graph: KnowledgeGraph,
    catalog: FleetCatalog,
) -> list[SpecialistManifest]:
    nodes = {node.id: node for node in graph.nodes}
    relationships: dict[str, list[Any]] = {}
    for edge in graph.edges:
        relationships.setdefault(edge.source, []).append(edge)
        relationships.setdefault(edge.target, []).append(edge)

    tool_by_capability: dict[str, set[str]] = {}
    tool_by_playbook: dict[str, set[str]] = {}
    for edge in graph.edges:
        if edge.source.startswith("tool:") and edge.target.startswith("capability:"):
            tool_by_capability.setdefault(edge.target.removeprefix("capability:"), set()).add(
                edge.source.removeprefix("tool:")
            )
        if edge.source.startswith("tool:") and edge.target.startswith("playbook:"):
            tool_by_playbook.setdefault(edge.target.removeprefix("playbook:"), set()).add(
                edge.source.removeprefix("tool:")
            )

    manifests: list[SpecialistManifest] = []
    for node in graph.nodes:
        if node.kind != "specialist":
            continue
        edge_set = relationships.get(node.id, [])
        guilds = sorted(
            {
                edge.target.removeprefix("guild:")
                for edge in edge_set
                if edge.source == node.id and edge.kind == "member_of"
            }
        )
        capabilities = sorted(
            {
                edge.target.removeprefix("capability:")
                for edge in edge_set
                if edge.source == node.id and edge.kind == "has_capability"
            }
        )
        playbooks = sorted(
            {
                edge.target.removeprefix("playbook:")
                for edge in edge_set
                if edge.source == node.id and edge.kind in {"uses_template", "runs"}
            }
        )
        if not playbooks:
            playbooks = _infer_playbooks(capabilities=capabilities, tags=node.tags)

        memory_scopes = {"working", "long_term"}
        policy_ids = {"offline_strict"}
        for guild_id in guilds:
            memory_scopes.update(catalog.guild_defaults.get(guild_id, []))
            policy_ids.update(catalog.guild_policies.get(guild_id, []))
        if any(item.startswith("communications.") for item in capabilities):
            policy_ids.add("outbound_approval")

        tool_ids: set[str] = set()
        for capability_id in capabilities:
            tool_ids.update(tool_by_capability.get(capability_id, set()))
        for playbook_id in playbooks:
            tool_ids.update(tool_by_playbook.get(playbook_id, set()))
        if "long_term" in memory_scopes:
            tool_ids.update({"memory_search", "memory_write"})

        source_status = node.status
        runtime_status = (
            SpecialistStatus.ACTIVE
            if source_status == "active"
            else SpecialistStatus.SANDBOXED
        )
        manifests.append(
            SpecialistManifest(
                id=node.id.removeprefix("specialist:"),
                display_name=node.label,
                purpose=node.description,
                guilds=guilds or ([node.group] if node.group else ["commons"]),
                playbook_ids=playbooks,
                capability_ids=capabilities,
                tool_ids=sorted(tool_ids),
                memory_scope_ids=sorted(memory_scopes),
                policy_ids=sorted(policy_ids),
                model_ids=["mac_gemma"],
                tags=node.tags,
                status=runtime_status,
                source_status=source_status,
            )
        )
    return manifests


def _infer_playbooks(*, capabilities: list[str], tags: list[str]) -> list[str]:
    values = " ".join([*capabilities, *tags]).lower()
    selected: list[str] = []
    rules = (
        ("route_and_synthesize", ("coordination", "assistant", "route", "operator")),
        ("scheduled_review", ("calendar", "schedule", "routine", "observability")),
        ("research_with_provenance", ("knowledge", "papers", "market", "research", "travel")),
        ("analyze_and_compare", ("finance", "compare", "evaluate", "economics")),
        ("design_run_evaluate", ("experiment", "model", "software.change", "scientific")),
        ("adversarial_review", ("policy", "safety", "risk", "verify_claims")),
        ("plan_and_operate", ("household", "shopping", "product", "software", "startup", "communications")),
    )
    for playbook_id, terms in rules:
        if any(term in values for term in terms):
            selected.append(playbook_id)
    return selected or ["route_and_synthesize"]


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(value.lower())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _validate_unique(kind: str, identifiers: list[str]) -> set[str]:
    duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
    if duplicates:
        raise ValueError(f"Duplicate {kind} identifiers: {', '.join(duplicates)}")
    return set(identifiers)


def _as_unique_map(kind: str, values: list[Any]) -> dict[str, Any]:
    _validate_unique(kind, [item.id for item in values])
    return {item.id: item for item in values}
