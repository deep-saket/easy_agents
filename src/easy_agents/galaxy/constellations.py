"""Created: 2026-09-24

Purpose: Defines typed Orbits and connected Constellation graph overlays.
"""

from __future__ import annotations

from collections import defaultdict, deque

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easy_agents.galaxy.enums import OrbitKind
from easy_agents.galaxy.identity import CircleId, ConstellationId, EntityRef, Identifier


class Orbit(BaseModel):
    """Represents one typed, directed relationship between canonical entities."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: Identifier
    source: EntityRef
    target: EntityRef
    kind: OrbitKind
    label: str = Field(min_length=1, max_length=160)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_self_loop(self) -> "Orbit":
        """Rejects accidental self-referential graph edges."""

        if self.source == self.target:
            raise ValueError(f"Orbit {self.id!r} cannot point an entity to itself.")
        return self


class Constellation(BaseModel):
    """A connected operational graph drawn from one or more Circles.

    A Constellation references entities but owns none of them. It is useful for
    describing a coherent workflow or collaboration spanning partial Circles.
    Routing never requires Constellation as an intermediate hop.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: ConstellationId
    display_name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4_000)
    circle_ids: tuple[CircleId, ...] = Field(min_length=1)
    nodes: tuple[EntityRef, ...] = Field(min_length=1)
    orbits: tuple[Orbit, ...] = ()
    tags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_connected_graph(self) -> "Constellation":
        """Rejects duplicates, dangling Orbits, and disconnected subgraphs."""

        node_keys = [(item.kind, item.id) for item in self.nodes]
        if len(node_keys) != len(set(node_keys)):
            raise ValueError(f"Constellation {self.id!r} contains duplicate nodes.")
        orbit_ids = [item.id for item in self.orbits]
        if len(orbit_ids) != len(set(orbit_ids)):
            raise ValueError(f"Constellation {self.id!r} contains duplicate Orbits.")
        known = set(node_keys)
        dangling = sorted(
            endpoint.canonical_id
            for orbit in self.orbits
            for endpoint in (orbit.source, orbit.target)
            if (endpoint.kind, endpoint.id) not in known
        )
        if dangling:
            raise ValueError(
                f"Constellation {self.id!r} has dangling endpoints: "
                + ", ".join(sorted(set(dangling)))
            )
        if len(known) > 1 and not _is_connected(self.nodes, self.orbits):
            raise ValueError(f"Constellation {self.id!r} must be a connected graph.")
        if len(self.circle_ids) != len(set(self.circle_ids)):
            raise ValueError(f"Constellation {self.id!r} contains duplicate Circles.")
        return self


def _is_connected(nodes: tuple[EntityRef, ...], orbits: tuple[Orbit, ...]) -> bool:
    """Checks weak connectivity because Orbits are directed operational edges."""

    graph: dict[tuple[object, str], set[tuple[object, str]]] = defaultdict(set)
    for orbit in orbits:
        source = (orbit.source.kind, orbit.source.id)
        target = (orbit.target.kind, orbit.target.id)
        graph[source].add(target)
        graph[target].add(source)
    start = (nodes[0].kind, nodes[0].id)
    visited = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor in graph[current] - visited:
            visited.add(neighbor)
            queue.append(neighbor)
    return len(visited) == len(nodes)
