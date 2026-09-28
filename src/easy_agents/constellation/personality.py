"""Created: 2026-09-27

Purpose: Defines the Galaxy Identity Circle as keyed, read-only documentation.

The Identity Circle contains no executing Planet.  Its documents describe the
Galaxy's name, role, personality, capabilities, architecture, and boundaries.
Gemma may select relevant document keys, but only deterministic schema and key
validation happen in code; no keyword router chooses semantic identity pages.
"""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from easy_agents.galaxy.registry import GalaxyRegistry


IdentityDocumentKey = Literal[
    "name",
    "role",
    "personality",
    "voice",
    "values",
    "capabilities",
    "boundaries",
    "architecture",
    "storage",
    "terminology",
]

IDENTITY_DOCUMENT_DEFINITIONS: tuple[
    tuple[IdentityDocumentKey, str, str], ...
] = (
    ("name", "Name", "The stable public name and ownership identity of this Galaxy."),
    ("role", "Role", "Why the Galaxy exists and the kinds of work it supports."),
    ("personality", "Personality", "The behavioral traits that shape every response."),
    ("voice", "Voice", "The communication principles used when speaking with the owner."),
    ("values", "Values", "The principles used to judge good assistance and system design."),
    ("capabilities", "Capabilities", "Semantic abilities and currently supported Chat actions."),
    ("boundaries", "Boundaries", "Honest limitations, safety limits, and disabled effects."),
    ("architecture", "Architecture", "Live topology facts and the Wormhole routing model."),
    ("storage", "Storage", "The distinct local history, journal, Vault, and artifact surfaces."),
    ("terminology", "Terminology", "The canonical language used throughout the agent system."),
)


class _IdentityModel(BaseModel):
    """Strict immutable base for Identity Circle contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class GalaxyTechnicalIdentity(_IdentityModel):
    """Live implementation facts used by architecture documentation."""

    ingress: str
    route: str
    galaxy_count: int = Field(ge=1)
    circle_count: int = Field(ge=1)
    planet_count: int = Field(ge=1)
    component_count: int = Field(ge=0)
    satellite_count: int = Field(ge=0)
    constellation_count: int = Field(ge=0)
    rogue_star_count: int = Field(ge=0)
    reasoning_model: str
    supported_chat_actions: tuple[str, ...]
    autonomous_external_effects: Literal[False] = False


IdentityDocumentValue = str | int | bool | tuple[str, ...]


class IdentityDocument(_IdentityModel):
    """One addressable key/value page in the Galaxy Identity Circle."""

    key: IdentityDocumentKey
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=500)
    entries: dict[str, IdentityDocumentValue] = Field(min_length=1)
    source: Literal["declarative", "live_registry", "mixed"]
    read_only: Literal[True] = True


class GalaxyIdentityLibrary(_IdentityModel):
    """Versioned key/value documentation library owned by Galaxy Identity.

    ``executing_planet_ids`` is intentionally constrained to an empty tuple.
    Operational answers use an ordinary Planet from an operational Circle and
    receive only the identity pages selected by Gemma as read-only context.
    """

    version: Literal[2] = 2
    circle_id: Literal["galaxy_identity"] = "galaxy_identity"
    circle_name: Literal["Galaxy Identity Circle"] = "Galaxy Identity Circle"
    circle_type: Literal["documentation"] = "documentation"
    description: str = (
        "A read-only keyed documentation Circle describing the Galaxy itself."
    )
    executing_planet_ids: tuple[str, ...] = Field(default=(), max_length=0)
    documents: dict[IdentityDocumentKey, IdentityDocument]

    @model_validator(mode="after")
    def validate_document_index(self) -> "GalaxyIdentityLibrary":
        """Ensures every dictionary key matches its document and no page is missing."""

        expected = {item[0] for item in IDENTITY_DOCUMENT_DEFINITIONS}
        if set(self.documents) != expected:
            missing = sorted(expected - set(self.documents))
            extra = sorted(set(self.documents) - expected)
            raise ValueError(
                f"Identity document index mismatch; missing={missing}, extra={extra}."
            )
        mismatched = sorted(
            key for key, document in self.documents.items() if key != document.key
        )
        if mismatched:
            raise ValueError(
                "Identity document keys do not match their pages: "
                + ", ".join(mismatched)
            )
        return self

    def document(self, key: IdentityDocumentKey) -> IdentityDocument:
        """Returns one validated identity page by its stable key."""

        return self.documents[key]

    def select(
        self, keys: Iterable[IdentityDocumentKey]
    ) -> tuple[IdentityDocument, ...]:
        """Projects model-selected keys into ordered, deduplicated pages."""

        selected: list[IdentityDocument] = []
        seen: set[str] = set()
        for key in keys:
            if key not in seen:
                selected.append(self.documents[key])
                seen.add(key)
        return tuple(selected)

    @classmethod
    def from_registry(
        cls,
        registry: GalaxyRegistry,
        *,
        supported_chat_actions: Iterable[str],
    ) -> "GalaxyIdentityLibrary":
        """Builds declarative pages with live facts from the active registry."""

        technical = GalaxyTechnicalIdentity(
            ingress="Wormhole",
            route="Wormhole -> Galaxy -> operational Circle -> accountable Planet",
            galaxy_count=len(registry.galaxies),
            circle_count=len(registry.circles),
            planet_count=len(registry.planets),
            component_count=len(registry.components),
            satellite_count=len(registry.satellites),
            constellation_count=len(registry.constellations),
            rogue_star_count=len(registry.rogue_stars),
            reasoning_model=(
                "gemma-4-E4B through the external Mac Gemma Rogue Star"
            ),
            supported_chat_actions=tuple(supported_chat_actions),
        )
        definitions = {
            key: (title, summary)
            for key, title, summary in IDENTITY_DOCUMENT_DEFINITIONS
        }

        def page(
            key: IdentityDocumentKey,
            entries: dict[str, IdentityDocumentValue],
            *,
            source: Literal["declarative", "live_registry", "mixed"] = "declarative",
        ) -> IdentityDocument:
            title, summary = definitions[key]
            return IdentityDocument(
                key=key,
                title=title,
                summary=summary,
                entries=entries,
                source=source,
            )

        documents = {
            "name": page(
                "name",
                {
                    "display_name": "Personal Agent Galaxy",
                    "short_name": "the Galaxy",
                    "owner_model": "one private Galaxy owned by its user",
                    "identity_circle": "Galaxy Identity Circle",
                },
            ),
            "role": page(
                "role",
                {
                    "purpose": (
                        "Help its owner think, remember, plan, explore, and carry "
                        "out bounded work across daily life, employment, science, "
                        "and future venture exploration."
                    ),
                    "operating_style": "local-first, evidence-oriented, and user-controlled",
                },
            ),
            "personality": page(
                "personality",
                {
                    "traits": (
                        "curious and intellectually adventurous",
                        "calm, candid, and clear about uncertainty",
                        "practical and biased toward reversible next steps",
                        "warm without pretending to be human",
                        "safety-conscious without becoming obstructive",
                    )
                },
            ),
            "voice": page(
                "voice",
                {
                    "principles": (
                        "answer directly before adding detail",
                        "use plain language and concrete examples",
                        "separate facts, assumptions, hypotheses, and recommendations",
                        "match technical depth to the question",
                    )
                },
            ),
            "values": page(
                "values",
                {
                    "principles": (
                        "user agency",
                        "privacy and local-first operation",
                        "truthfulness about capabilities and limitations",
                        "evidence, provenance, and reproducibility",
                        "small reusable components and accountable ownership",
                    )
                },
            ),
            "capabilities": page(
                "capabilities",
                {
                    "semantic_capabilities": (
                        "organize daily life, household work, schedules, and personal knowledge",
                        "brainstorm and evaluate scientific or deep-tech opportunities",
                        "support energy, satellite, medical, and software exploration",
                        "plan and compare work, preserve evidence, and propose experiments",
                        "explain its architecture, terminology, and runtime state",
                    ),
                    "chat_actions": technical.supported_chat_actions,
                },
                source="mixed",
            ),
            "boundaries": page(
                "boundaries",
                {
                    "rules": (
                        "never claim an external action without verified Satellite evidence",
                        "never autonomously call, send, buy, pay, or publish",
                        "keep employer, personal, exploration, and company scopes separate",
                        "never replace qualified medical, legal, financial, or safety experts",
                        "never invent access to memories, providers, sources, or measurements",
                    ),
                    "autonomous_external_effects": False,
                },
            ),
            "architecture": page(
                "architecture",
                {
                    "ingress": technical.ingress,
                    "operational_route": technical.route,
                    "identity_circle_route_status": "documentation context only; never a Mission hop",
                    "galaxies": technical.galaxy_count,
                    "circles": technical.circle_count,
                    "planets": technical.planet_count,
                    "components": technical.component_count,
                    "satellites": technical.satellite_count,
                    "constellations": technical.constellation_count,
                    "rogue_stars": technical.rogue_star_count,
                    "reasoning_model": technical.reasoning_model,
                },
                source="live_registry",
            ),
            "storage": page(
                "storage",
                {
                    "surfaces": (
                        "bounded SQLite conversation history",
                        "typed Commons Vault memory",
                        "per-conversation JSON exploration journals",
                        "versioned local artifacts and evidence records",
                    )
                },
            ),
            "terminology": page(
                "terminology",
                {
                    "terms": (
                        "Galaxy: top-level owned agent system",
                        "Circle: owned grouping of related Planets or Components",
                        "Planet: executing agent",
                        "Satellite: callable tool Component",
                        "Constellation: connected graph overlay across Circles",
                        "Wormhole: controlled Galaxy ingress",
                        "Rogue Star: shared external resource outside every Galaxy",
                    )
                },
            ),
        }
        return cls(documents=documents)


class IdentityDocumentSelectionPlan(_IdentityModel):
    """Gemma-selected identity keys before their pages are retrieved."""

    keys: tuple[IdentityDocumentKey, ...] = Field(min_length=1, max_length=5)
    reasoning_summary: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_unique_keys(self) -> "IdentityDocumentSelectionPlan":
        """Rejects duplicate page keys rather than silently changing model output."""

        if len(self.keys) != len(set(self.keys)):
            raise ValueError("Identity document selection contains duplicate keys.")
        return self


class IdentityDocumentSelectionRequest(_IdentityModel):
    """Natural-language request for Gemma-selected identity documentation."""

    query: str = Field(min_length=1, max_length=4_000)


class IdentityDocumentSelectionResult(_IdentityModel):
    """Validated model selection plus the retrieved read-only pages."""

    query: str
    keys: tuple[IdentityDocumentKey, ...]
    reasoning_summary: str
    documents: tuple[IdentityDocument, ...]
    model_id: str
    attempts: int = Field(ge=1, le=2)
    duration_ms: float = Field(ge=0)


class GalaxyIdentitySelector:
    """Uses Gemma to choose identity-document keys without keyword fallback."""

    def __init__(
        self,
        library: GalaxyIdentityLibrary,
        *,
        llm: Any,
        max_attempts: int = 2,
    ) -> None:
        self.library = library
        self.llm = llm
        self.max_attempts = max_attempts

    def select(self, query: str) -> IdentityDocumentSelectionResult:
        """Selects and retrieves the smallest useful set of identity pages."""

        generate = getattr(self.llm, "structured_generate", None)
        if not callable(generate):
            raise RuntimeError("Gemma structured generation is unavailable.")
        index = [
            {"key": document.key, "title": document.title, "summary": document.summary}
            for document in self.library.documents.values()
        ]
        base_prompt = f"""Choose the smallest useful set of Galaxy Identity document keys
for the user's question. This Circle is read-only documentation and has no executing
Planets. Return only schema-valid JSON; do not answer the question itself.

Document index:
{json.dumps(index, ensure_ascii=False)}

User question: {query}"""
        started = perf_counter()
        correction = ""
        model_id = str(getattr(self.llm, "model_name", type(self.llm).__name__))
        for attempt in range(1, self.max_attempts + 1):
            try:
                plan = generate(
                    f"{base_prompt}{correction}",
                    IdentityDocumentSelectionPlan,
                    max_tokens=256,
                )
                if not isinstance(plan, IdentityDocumentSelectionPlan):
                    plan = IdentityDocumentSelectionPlan.model_validate(plan)
                return IdentityDocumentSelectionResult(
                    query=query,
                    keys=plan.keys,
                    reasoning_summary=plan.reasoning_summary,
                    documents=self.library.select(plan.keys),
                    model_id=model_id,
                    attempts=attempt,
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                )
            except (TypeError, ValueError, ValidationError) as exc:
                if attempt == self.max_attempts:
                    raise
                correction = (
                    "\nThe previous key selection was invalid. Return one corrected "
                    f"object. Validation feedback: {type(exc).__name__}: {exc}"
                )[:1_000]
        raise AssertionError("unreachable identity selection loop")
