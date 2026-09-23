"""Hierarchical Wormhole routing into the personal Galaxy."""

from __future__ import annotations

import re

from easy_agents.fleet.models import (
    CircleRouteCandidate,
    GalaxyRoutePlan,
    MissionRequest,
    RouteCandidate,
    RoutingPath,
    SpecialistStatus,
)
from easy_agents.fleet.registry import FleetRegistry


WORMHOLE_ID = "service:wormhole"
WORMHOLE_NAME = "Wormhole"
DEFAULT_GALAXY_ID = "personal"
DEFAULT_GALAXY_NAME = "Personal Agent Galaxy"

# Compatibility aliases for callers that used the implementation vocabulary.
ENTRYPOINT_ID = WORMHOLE_ID
ENTRYPOINT_NAME = WORMHOLE_NAME

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

_CIRCLE_ALIASES: dict[str, tuple[str, ...]] = {
    "commons": ("assistant", "help", "daily", "priorities", "coordinate", "route"),
    "home": ("chores", "groceries", "shopping", "mom", "dad", "parents", "family"),
    "life_admin": ("appointment", "calendar", "travel", "passport", "reminder", "documents"),
    "wellbeing": ("health", "fitness", "meal", "learning", "wellbeing"),
    "science_lab": ("science", "scientific", "paper", "literature", "hypothesis", "experiment"),
    "venture_studio": ("startup", "business", "product", "customer", "market", "fundraising"),
    "engineering": ("software", "code", "coding", "engineering", "deploy", "infrastructure"),
    "finance": ("finance", "budget", "bill", "tax", "bookkeeping", "payment"),
    "communications": ("email", "message", "whatsapp", "write", "presentation", "publish"),
    "employment": ("employer", "employment", "work", "nda", "confidential", "intellectual property"),
    "venture_exploration": (
        "brainstorm",
        "idea",
        "ideas",
        "opportunity",
        "thesis",
        "deep tech",
        "invention",
    ),
    "energy": ("energy", "battery", "storage", "hydrogen", "grid", "power", "decarbonization"),
    "satcom": ("satcom", "satellite", "rf", "link budget", "orbit", "spectrum", "space"),
    "medical_deeptech": (
        "medical",
        "clinical",
        "hospital",
        "diagnostic",
        "biotechnology",
        "healthcare",
    ),
}


class WormholeRouter:
    """Accepts a Mission and routes it into the Galaxy and its Circles."""

    def __init__(self, registry: FleetRegistry) -> None:
        self.registry = registry
        self._nodes = {node.id: node for node in registry.graph.nodes}

    def route(self, request: MissionRequest) -> GalaxyRoutePlan:
        """Returns a deterministic, explainable hierarchical routing plan."""

        if request.specialist_id:
            candidates = self._explicit_team(request)
            circles = self._circles_for_candidates(request.objective, candidates)
        else:
            circles = self._rank_circles(
                request.objective,
                limit=min(max(request.team_size, 1), 3),
            )
            candidates = self._team_for_circles(
                request.objective,
                circles=circles,
                limit=request.team_size,
            )
            circles = self._attach_selected_specialists(circles, candidates)

        paths = self._paths(circles, candidates)
        return GalaxyRoutePlan(
            objective=request.objective,
            wormhole_id=WORMHOLE_ID,
            wormhole_name=WORMHOLE_NAME,
            galaxy_id=DEFAULT_GALAXY_ID,
            galaxy_name=DEFAULT_GALAXY_NAME,
            circles=circles,
            candidates=candidates,
            paths=paths,
        )

    def _explicit_team(self, request: MissionRequest) -> list[RouteCandidate]:
        manifest = self.registry.get_specialist(str(request.specialist_id))
        explicit = RouteCandidate(
            specialist_id=manifest.id,
            display_name=manifest.display_name,
            score=1.0,
            matched_terms=["explicit-selection"],
            status=manifest.status,
            guilds=manifest.guilds,
        )
        if request.team_size == 1:
            return [explicit]
        additional = [
            item
            for item in self.registry.route(
                request.objective,
                limit=len(self.registry.specialists),
            )
            if item.specialist_id != manifest.id
        ]
        return [explicit, *additional[: request.team_size - 1]]

    def _rank_circles(self, objective: str, *, limit: int) -> list[CircleRouteCandidate]:
        query_terms = _tokens(objective)
        candidates: list[CircleRouteCandidate] = []
        guild_nodes = [node for node in self.registry.graph.nodes if node.kind == "guild"]
        for node in guild_nodes:
            circle_id = node.id.removeprefix("guild:")
            weighted_terms: dict[str, float] = {}
            _add_terms(weighted_terms, f"{node.label} {circle_id.replace('_', ' ')}", 3.0)
            _add_terms(weighted_terms, " ".join(_CIRCLE_ALIASES.get(circle_id, ())), 3.3)
            _add_terms(weighted_terms, " ".join(node.tags), 2.5)
            _add_terms(weighted_terms, node.description, 1.3)
            for manifest in self.registry.specialists.values():
                if circle_id not in manifest.guilds:
                    continue
                _add_terms(weighted_terms, " ".join(manifest.tags), 0.9)
                _add_terms(weighted_terms, manifest.purpose, 0.55)
            matched = sorted(query_terms & set(weighted_terms))
            raw_score = sum(weighted_terms[token] for token in matched)
            phrase_bonus = 2.0 if node.label.lower() in objective.lower() else 0.0
            score = min(
                1.0,
                (raw_score + phrase_bonus) / max(len(query_terms) * 2.7, 4.0),
            )
            if score <= 0:
                continue
            candidates.append(
                CircleRouteCandidate(
                    circle_id=circle_id,
                    display_name=node.label,
                    score=round(score, 4),
                    matched_terms=matched,
                    status=node.status,
                )
            )
        candidates.sort(key=lambda item: (-item.score, item.display_name.lower(), item.circle_id))
        if candidates:
            threshold = max(0.1, candidates[0].score * 0.25)
            qualifying = [item for item in candidates if item.score >= threshold]
            return qualifying[: max(1, limit)]
        fallback = self._nodes.get("guild:commons") or sorted(
            guild_nodes,
            key=lambda item: (item.label.lower(), item.id),
        )[0]
        return [
            CircleRouteCandidate(
                circle_id=fallback.id.removeprefix("guild:"),
                display_name=fallback.label,
                score=0.1,
                matched_terms=[],
                status=fallback.status,
            )
        ]

    def _team_for_circles(
        self,
        objective: str,
        *,
        circles: list[CircleRouteCandidate],
        limit: int,
    ) -> list[RouteCandidate]:
        ranked = self.registry.route(objective, limit=len(self.registry.specialists))
        selected: list[RouteCandidate] = []
        selected_ids: set[str] = set()
        for circle in circles:
            match = next(
                (
                    item
                    for item in ranked
                    if item.specialist_id not in selected_ids
                    and circle.circle_id in item.guilds
                ),
                None,
            )
            if match is not None:
                selected.append(match)
                selected_ids.add(match.specialist_id)
            if len(selected) >= limit:
                return selected

        selected_circles = {item.circle_id for item in circles}
        for item in ranked:
            if item.specialist_id in selected_ids:
                continue
            if not selected_circles.intersection(item.guilds):
                continue
            selected.append(item)
            selected_ids.add(item.specialist_id)
            if len(selected) >= limit:
                break

        if selected:
            return selected
        fallback_manifests = [
            item
            for item in self.registry.list_specialists()
            if selected_circles.intersection(item.guilds)
        ]
        if not fallback_manifests:
            fallback_manifests = [self.registry.get_specialist("personal_steward")]
        manifest = min(
            fallback_manifests,
            key=lambda item: (
                item.status != SpecialistStatus.ACTIVE,
                item.display_name.lower(),
                item.id,
            ),
        )
        return [
            RouteCandidate(
                specialist_id=manifest.id,
                display_name=manifest.display_name,
                score=0.1,
                matched_terms=[],
                status=manifest.status,
                guilds=manifest.guilds,
            )
        ]

    def _circles_for_candidates(
        self,
        objective: str,
        candidates: list[RouteCandidate],
    ) -> list[CircleRouteCandidate]:
        ranked = self._rank_circles(objective, limit=3)
        rank_by_id = {item.circle_id: item for item in ranked}
        chosen: dict[str, CircleRouteCandidate] = {}
        for candidate in candidates:
            circle_id = next(
                (item.circle_id for item in ranked if item.circle_id in candidate.guilds),
                candidate.guilds[0],
            )
            circle = rank_by_id.get(circle_id)
            if circle is None:
                node = self._nodes[f"guild:{circle_id}"]
                circle = CircleRouteCandidate(
                    circle_id=circle_id,
                    display_name=node.label,
                    score=1.0 if candidate.score == 1.0 else candidate.score,
                    matched_terms=list(candidate.matched_terms),
                    status=node.status,
                )
            chosen.setdefault(circle_id, circle)
        return self._attach_selected_specialists(list(chosen.values()), candidates)

    @staticmethod
    def _attach_selected_specialists(
        circles: list[CircleRouteCandidate],
        candidates: list[RouteCandidate],
    ) -> list[CircleRouteCandidate]:
        attached: list[CircleRouteCandidate] = []
        for circle in circles:
            selected_ids = [
                item.specialist_id
                for item in candidates
                if circle.circle_id in item.guilds
            ]
            if not selected_ids:
                continue
            attached.append(
                circle.model_copy(update={"selected_specialist_ids": selected_ids})
            )
        return attached

    @staticmethod
    def _paths(
        circles: list[CircleRouteCandidate],
        candidates: list[RouteCandidate],
    ) -> list[RoutingPath]:
        paths: list[RoutingPath] = []
        for candidate in candidates:
            circle_id = next(
                (
                    item.circle_id
                    for item in circles
                    if item.circle_id in candidate.guilds
                ),
                candidate.guilds[0],
            )
            paths.append(
                RoutingPath(
                    wormhole_id=WORMHOLE_ID,
                    galaxy_id=DEFAULT_GALAXY_ID,
                    circle_id=circle_id,
                    specialist_id=candidate.specialist_id,
                )
            )
        return paths


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(value.lower())
        if token not in _STOP_WORDS and len(token) > 1
    }


def _add_terms(target: dict[str, float], value: str, weight: float) -> None:
    for token in _tokens(value):
        target[token] = max(target.get(token, 0.0), weight)


# Kept as a source-compatible alias while the public terminology moves to Wormhole.
ConstellationGateway = WormholeRouter
