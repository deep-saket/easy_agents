"""Typed, reusable knowledge-graph projection for the Constellation UI."""

from __future__ import annotations

from collections import Counter
from importlib import resources
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from easy_agents.constellation.directory import ConstellationDirectory


GraphNodeKind = Literal[
    "galaxy",
    "rogue_star",
    "constellation",
    "specialist",
    "guild",
    "capability",
    "tool",
    "memory",
    "playbook",
    "policy",
    "model",
    "service",
]


class KnowledgeGraphNode(BaseModel):
    """One inspectable entity in the Constellation graph."""

    id: str
    kind: GraphNodeKind
    label: str
    description: str = ""
    status: str = "available"
    group: str | None = None
    tags: list[str] = Field(default_factory=list)
    risk: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphEdge(BaseModel):
    """One typed relationship between graph entities."""

    id: str
    source: str
    target: str
    kind: str
    label: str
    directed: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraph(BaseModel):
    """Complete graph payload consumed by the local visualization."""

    version: Literal[1] = 1
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]
    counts: dict[str, int]

    @model_validator(mode="after")
    def validate_graph(self) -> "KnowledgeGraph":
        node_ids = [node.id for node in self.nodes]
        edge_ids = [edge.id for edge in self.edges]
        duplicate_nodes = sorted(
            value for value, count in Counter(node_ids).items() if count > 1
        )
        duplicate_edges = sorted(
            value for value, count in Counter(edge_ids).items() if count > 1
        )
        if duplicate_nodes:
            raise ValueError(
                "Duplicate knowledge-graph node identifiers: "
                + ", ".join(duplicate_nodes)
            )
        if duplicate_edges:
            raise ValueError(
                "Duplicate knowledge-graph edge identifiers: "
                + ", ".join(duplicate_edges)
            )
        known_nodes = set(node_ids)
        missing = sorted(
            {
                endpoint
                for edge in self.edges
                for endpoint in (edge.source, edge.target)
                if endpoint not in known_nodes
            }
        )
        if missing:
            raise ValueError(
                "Knowledge-graph edges reference unknown nodes: "
                + ", ".join(missing)
            )
        return self


class OverlayGuild(BaseModel):
    """Planned domain group added to the current Roster projection."""

    id: str
    label: str
    description: str
    tags: list[str] = Field(default_factory=list)


class OverlaySpecialist(BaseModel):
    """Planned Specialist and its reusable graph-template bindings."""

    id: str
    label: str
    description: str
    guild: str
    templates: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: str = "sandboxed"


class OverlayComponent(BaseModel):
    """A non-agent component represented as a first-class graph node."""

    id: str
    kind: Literal["tool", "memory", "playbook", "policy", "model", "service"]
    label: str
    description: str
    status: str = "available"
    group: str | None = None
    tags: list[str] = Field(default_factory=list)
    risk: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OverlayRelation(BaseModel):
    """Curated relationship not inferable from the current Roster."""

    source: str
    target: str
    kind: str
    label: str
    directed: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphOverlay(BaseModel):
    """Validated planned-role and shared-component overlay."""

    version: Literal[1] = 1
    guilds: list[OverlayGuild] = Field(default_factory=list)
    specialists: list[OverlaySpecialist] = Field(default_factory=list)
    components: list[OverlayComponent] = Field(default_factory=list)
    relations: list[OverlayRelation] = Field(default_factory=list)


def load_default_overlay() -> KnowledgeGraphOverlay:
    """Loads the packaged deep-tech and shared-component graph overlay."""

    overlay_text = (
        resources.files("easy_agents.constellation")
        .joinpath("knowledge_graph.yaml")
        .read_text(encoding="utf-8")
    )
    payload = yaml.safe_load(overlay_text)
    if not isinstance(payload, dict):
        raise ValueError("Knowledge-graph overlay must be a YAML mapping.")
    return KnowledgeGraphOverlay.model_validate(payload)


def build_knowledge_graph(
    directory: ConstellationDirectory | None = None,
    overlay: KnowledgeGraphOverlay | None = None,
) -> KnowledgeGraph:
    """Projects the current Roster and planned components into one graph."""

    active_directory = directory or ConstellationDirectory.default()
    active_overlay = overlay or load_default_overlay()
    nodes: list[KnowledgeGraphNode] = []
    edges: list[KnowledgeGraphEdge] = []

    nodes.append(
        KnowledgeGraphNode(
            id="service:wormhole",
            kind="service",
            label="Wormhole",
            description=(
                "The Galaxy's single ingress router. It accepts a Mission, selects "
                "one or more Circles, and produces an explainable Trajectory."
            ),
            status="implemented",
            tags=["entrypoint", "wormhole", "route", "dispatch", "conversation"],
            metadata={
                "entrypoint": True,
                "route_api": "/api/wormhole/route",
                "flow": "Wormhole → Galaxy → Circle → Planet",
            },
        )
    )
    nodes.append(
        KnowledgeGraphNode(
            id="galaxy:personal",
            kind="galaxy",
            label="Personal Agent Galaxy",
            description=(
                "The top-level owned system containing this user's Circles, "
                "connected Constellation overlays, governance, and shared services."
            ),
            status="active",
            tags=["personal", "ownership-boundary", "agent-system"],
            metadata={"default": True},
        )
    )
    nodes.append(
        KnowledgeGraphNode(
            id="constellation:personal_operations",
            kind="constellation",
            label="Personal Operations Constellation",
            description=(
                "A connected operational subgraph drawn from parts of one or more "
                "Circles for personal life, employment, scientific exploration, "
                "and venture discovery. It is an overlay, not a routing layer."
            ),
            status="active",
            tags=["personal", "work", "science", "venture", "connected-system"],
            metadata={
                "galaxy_id": "personal",
                "default": True,
                "routing_layer": False,
                "circle_scope": "one_or_more_partial",
            },
        )
    )
    edges.append(
        _edge(
            source="service:wormhole",
            target="galaxy:personal",
            kind="enters_galaxy",
            label="enters Galaxy",
        )
    )
    for guild in active_directory.guilds.values():
        nodes.append(
            KnowledgeGraphNode(
                id=f"guild:{guild.id}",
                kind="guild",
                label=guild.display_name,
                description=guild.purpose,
                status="active",
                tags=guild.tags,
                metadata={
                    "member_term": "Circle Member",
                    "member_types": [
                        "Rocky Planet",
                        "Giant Planet",
                        "Component",
                    ],
                },
            )
        )

    for capability in active_directory.capabilities.values():
        nodes.append(
            KnowledgeGraphNode(
                id=f"capability:{capability.id}",
                kind="capability",
                label=capability.display_name,
                description=capability.description,
                status="implemented",
                tags=capability.tags,
                risk=capability.risk.value,
                metadata={
                    "effects": capability.effects,
                    "network_required": capability.network_required,
                    "approval_required": capability.approval_required,
                },
            )
        )

    for specialist in active_directory.specialists.values():
        specialist_id = f"specialist:{specialist.id}"
        nodes.append(
            KnowledgeGraphNode(
                id=specialist_id,
                kind="specialist",
                label=specialist.display_name,
                description=specialist.purpose,
                status=specialist.status.value,
                group=specialist.guilds[0],
                tags=specialist.tags,
                metadata={
                    "agent_type": "specialist",
                    "planet_class": "rocky_planet",
                    "liaison": specialist.liaison,
                    "source": "roster",
                },
            )
        )
        for guild_id in specialist.guilds:
            edges.append(
                _edge(
                    source=specialist_id,
                    target=f"guild:{guild_id}",
                    kind="member_of",
                    label="member of",
                )
            )
        for capability_id in specialist.capability_ids:
            edges.append(
                _edge(
                    source=specialist_id,
                    target=f"capability:{capability_id}",
                    kind="has_capability",
                    label="can use",
                )
            )

    known_ids = {node.id for node in nodes}
    for guild in active_overlay.guilds:
        node_id = f"guild:{guild.id}"
        if node_id in known_ids:
            continue
        nodes.append(
            KnowledgeGraphNode(
                id=node_id,
                kind="guild",
                label=guild.label,
                description=guild.description,
                status="planned",
                tags=guild.tags,
                metadata={
                    "member_term": "Circle Member",
                    "member_types": [
                        "Rocky Planet",
                        "Giant Planet",
                        "Component",
                    ],
                },
            )
        )
        known_ids.add(node_id)

    for node in [item for item in nodes if item.kind == "guild"]:
        edges.append(
            _edge(
                source="galaxy:personal",
                target=node.id,
                kind="contains_circle",
                label="contains Circle",
            )
        )
        edges.append(
            _edge(
                source="constellation:personal_operations",
                target=node.id,
                kind="spans_circle",
                label="spans part of Circle",
            )
        )

    for component in active_overlay.components:
        node_id = f"{component.kind}:{component.id}"
        is_rogue_star = component.metadata.get("topology_role") == "rogue_star"
        node_kind: GraphNodeKind = "rogue_star" if is_rogue_star else component.kind
        component_metadata = dict(component.metadata)
        if is_rogue_star:
            component_metadata["resource_kind"] = component.kind
        nodes.append(
            KnowledgeGraphNode(
                id=node_id,
                kind=node_kind,
                label=component.label,
                description=component.description,
                status=component.status,
                group=component.group,
                tags=component.tags,
                risk=component.risk,
                metadata=component_metadata,
            )
        )
        known_ids.add(node_id)
        if is_rogue_star:
            edges.append(
                _edge(
                    source="galaxy:personal",
                    target=node_id,
                    kind="accesses_external",
                    label="accesses Rogue Star",
                    metadata={"ownership": False, "cross_galaxy": True},
                )
            )

    for specialist in active_overlay.specialists:
        specialist_id = f"specialist:{specialist.id}"
        nodes.append(
            KnowledgeGraphNode(
                id=specialist_id,
                kind="specialist",
                label=specialist.label,
                description=specialist.description,
                status=specialist.status,
                group=specialist.guild,
                tags=specialist.tags,
                metadata={
                    "agent_type": "specialist",
                    "planet_class": "rocky_planet",
                    "source": "deep-tech-plan",
                },
            )
        )
        edges.append(
            _edge(
                source=specialist_id,
                target=f"guild:{specialist.guild}",
                kind="member_of",
                label="member of",
            )
        )
        for template_id in specialist.templates:
            edges.append(
                _edge(
                    source=specialist_id,
                    target=f"playbook:{template_id}",
                    kind="uses_template",
                    label="uses template",
                )
            )
        known_ids.add(specialist_id)

    for membership in [item for item in edges if item.kind == "member_of"]:
        edges.append(
            _edge(
                source=membership.target,
                target=membership.source,
                kind="dispatches_to",
                label="dispatches to",
                metadata={"routing_only": True},
            )
        )

    for relation in active_overlay.relations:
        edges.append(
            _edge(
                source=relation.source,
                target=relation.target,
                kind=relation.kind,
                label=relation.label,
                directed=relation.directed,
                metadata=relation.metadata,
            )
        )

    counts = dict(sorted(Counter(node.kind for node in nodes).items()))
    return KnowledgeGraph(nodes=nodes, edges=edges, counts=counts)


def _edge(
    *,
    source: str,
    target: str,
    kind: str,
    label: str,
    directed: bool = True,
    metadata: dict[str, Any] | None = None,
) -> KnowledgeGraphEdge:
    """Builds a deterministic relationship identifier."""

    edge_id = f"{kind}:{source}->{target}"
    return KnowledgeGraphEdge(
        id=edge_id,
        source=source,
        target=target,
        kind=kind,
        label=label,
        directed=directed,
        metadata=metadata or {},
    )
