"""Created: 2026-09-24

Purpose: Composes canonical Wormhole routing with the working Fleet and Gemma runtime.
"""

from __future__ import annotations

import json
import sqlite3
from collections import OrderedDict, deque
from pathlib import Path
from threading import RLock
from time import time
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from easy_agents.fleet.model_profiles import MAC_GEMMA_PROFILE_ID
from easy_agents.fleet.models import GalaxyRoutePlan, MissionRequest
from easy_agents.fleet.runtime import FleetRuntime
from easy_agents.galaxy.enums import EntityKind
from easy_agents.galaxy.identity import Identifier
from easy_agents.galaxy.missions import Mission, Trajectory
from easy_agents.galaxy.registry import GalaxyRegistry
from easy_agents.galaxy.routing import Wormhole
from easy_agents.constellation.satellite_tools import (
    LocalSatelliteRuntime,
    PlannedSatelliteCall,
)


class ChatEntity(BaseModel):
    """Small canonical entity summary rendered in the chat trajectory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Identifier
    display_name: str = Field(min_length=1, max_length=160)
    status: str | None = Field(default=None, max_length=64)


class ChatTurn(BaseModel):
    """One bounded user or Galaxy message retained in local process memory."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class WormholeChatRequest(BaseModel):
    """User message submitted to the Galaxy through the Wormhole."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    message: str = Field(min_length=3, max_length=12_000)
    conversation_id: Identifier | None = None
    reset_conversation: bool = False


class ChatRouteContext(BaseModel):
    """Explains routed and supporting entities without changing route semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    galaxy: ChatEntity
    circles: tuple[ChatEntity, ...]
    planets: tuple[ChatEntity, ...]
    constellations: tuple[ChatEntity, ...] = ()
    available_satellites: tuple[ChatEntity, ...] = ()
    invoked_satellites: tuple[ChatEntity, ...] = ()
    rogue_stars: tuple[ChatEntity, ...] = ()


class SatelliteInvocation(BaseModel):
    """Auditable result of one real Satellite execution for a chat Mission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    satellite: ChatEntity
    status: Literal["completed"] = "completed"
    arguments: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=300)


class WormholeChatResponse(BaseModel):
    """Answer plus canonical trajectory and supporting operational context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: Identifier
    message_id: Identifier
    mission_id: Identifier
    status: str
    answer: str
    trajectory: Trajectory
    route_context: ChatRouteContext
    satellite_invocations: tuple[SatelliteInvocation, ...] = ()
    visualization_route: GalaxyRoutePlan
    used_model: str | None = None
    warnings: tuple[str, ...] = ()
    retained_turns: int = Field(ge=2)


class ConversationStore:
    """Thread-safe bounded conversation history with optional SQLite durability.

    With no ``db_path`` the store remains an isolated in-memory implementation
    suitable for tests and embedding.  A path enables process-restart-safe local
    history while retaining the same turn and conversation limits.  This is
    working conversation context, not automatically promoted long-term memory.
    """

    def __init__(
        self,
        *,
        max_conversations: int = 128,
        max_turns: int = 20,
        db_path: Path | None = None,
    ) -> None:
        """Creates a bounded store with least-recently-used conversation eviction."""

        if max_conversations < 1 or max_turns < 2:
            raise ValueError("Conversation limits must be positive and retain two turns.")
        self.max_conversations = max_conversations
        self.max_turns = max_turns
        self.db_path = db_path
        self._histories: OrderedDict[str, deque[ChatTurn]] = OrderedDict()
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        if db_path is not None:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(str(db_path), check_same_thread=False)
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_turns (
                    conversation_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (conversation_id, sequence)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_conversations (
                    conversation_id TEXT PRIMARY KEY,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._connection.commit()

    @property
    def backend(self) -> Literal["memory", "sqlite"]:
        """Returns the storage mode for readiness and documentation surfaces."""

        return "sqlite" if self._connection is not None else "memory"

    def read(self, conversation_id: str) -> tuple[ChatTurn, ...]:
        """Returns a snapshot and marks the conversation as recently used."""

        with self._lock:
            if self._connection is not None:
                rows = self._connection.execute(
                    """
                    SELECT role, content
                    FROM chat_turns
                    WHERE conversation_id = ?
                    ORDER BY sequence ASC
                    """,
                    (conversation_id,),
                ).fetchall()
                if not rows:
                    return ()
                self._touch_sqlite(conversation_id)
                self._connection.commit()
                return tuple(ChatTurn(role=row[0], content=row[1]) for row in rows)
            history = self._histories.get(conversation_id)
            if history is None:
                return ()
            self._histories.move_to_end(conversation_id)
            return tuple(history)

    def append(self, conversation_id: str, *turns: ChatTurn) -> tuple[ChatTurn, ...]:
        """Appends turns and evicts old turns and conversations deterministically."""

        with self._lock:
            if self._connection is not None:
                row = self._connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) FROM chat_turns WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()
                sequence = int(row[0]) if row else 0
                now = time()
                for turn in turns:
                    sequence += 1
                    self._connection.execute(
                        """
                        INSERT INTO chat_turns (
                            conversation_id, sequence, role, content, created_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (conversation_id, sequence, turn.role, turn.content, now),
                    )
                self._connection.execute(
                    """
                    DELETE FROM chat_turns
                    WHERE conversation_id = ? AND sequence NOT IN (
                        SELECT sequence FROM chat_turns
                        WHERE conversation_id = ?
                        ORDER BY sequence DESC
                        LIMIT ?
                    )
                    """,
                    (conversation_id, conversation_id, self.max_turns),
                )
                self._touch_sqlite(conversation_id)
                stale = self._connection.execute(
                    """
                    SELECT conversation_id FROM chat_conversations
                    ORDER BY updated_at DESC, conversation_id ASC
                    LIMIT -1 OFFSET ?
                    """,
                    (self.max_conversations,),
                ).fetchall()
                for (stale_id,) in stale:
                    self._connection.execute(
                        "DELETE FROM chat_turns WHERE conversation_id = ?",
                        (stale_id,),
                    )
                    self._connection.execute(
                        "DELETE FROM chat_conversations WHERE conversation_id = ?",
                        (stale_id,),
                    )
                self._connection.commit()
                rows = self._connection.execute(
                    """
                    SELECT role, content FROM chat_turns
                    WHERE conversation_id = ? ORDER BY sequence ASC
                    """,
                    (conversation_id,),
                ).fetchall()
                return tuple(ChatTurn(role=row[0], content=row[1]) for row in rows)
            history = self._histories.setdefault(
                conversation_id,
                deque(maxlen=self.max_turns),
            )
            history.extend(turns)
            self._histories.move_to_end(conversation_id)
            while len(self._histories) > self.max_conversations:
                self._histories.popitem(last=False)
            return tuple(history)

    def clear(self, conversation_id: str) -> None:
        """Removes one conversation if it exists."""

        with self._lock:
            if self._connection is not None:
                self._connection.execute(
                    "DELETE FROM chat_turns WHERE conversation_id = ?",
                    (conversation_id,),
                )
                self._connection.execute(
                    "DELETE FROM chat_conversations WHERE conversation_id = ?",
                    (conversation_id,),
                )
                self._connection.commit()
                return
            self._histories.pop(conversation_id, None)

    def close(self) -> None:
        """Closes the durable connection; in-memory stores require no action."""

        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _touch_sqlite(self, conversation_id: str) -> None:
        """Updates SQLite LRU metadata while the caller holds ``_lock``."""

        assert self._connection is not None
        self._connection.execute(
            """
            INSERT INTO chat_conversations (conversation_id, updated_at)
            VALUES (?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (conversation_id, time()),
        )


class WormholeChatService:
    """Routes a chat message and executes the selected Planet through Gemma.

    The canonical route remains ``Wormhole → Galaxy → Circle → Planet``.
    Constellations are reported as connected overlays containing the selected
    entities. Satellites are reported as tools available to the Planet; only a
    future tool-execution result may put a Satellite in ``invoked_satellites``.
    """

    def __init__(
        self,
        *,
        registry: GalaxyRegistry,
        fleet_runtime: FleetRuntime,
        history: ConversationStore | None = None,
        satellite_runtime: LocalSatelliteRuntime | None = None,
    ) -> None:
        """Composes routing, Fleet execution, Satellites, and chat history."""

        self.registry = registry
        self.fleet_runtime = fleet_runtime
        self.wormhole = Wormhole(registry)
        self.history = history or ConversationStore()
        self.satellite_runtime = satellite_runtime

    def chat(self, request: WormholeChatRequest) -> WormholeChatResponse:
        """Routes and answers one user message with bounded prior-turn context."""

        conversation_id = request.conversation_id or f"chat-{uuid4().hex}"
        if request.reset_conversation:
            self.history.clear(conversation_id)
        prior_turns = self.history.read(conversation_id)
        mission = Mission(objective=request.message, team_size=1)
        trajectory = self.wormhole.route(mission)
        planned_calls = (
            self.satellite_runtime.plan(
                request.message,
                conversation_id=conversation_id,
            )
            if self.satellite_runtime is not None
            else ()
        )
        trajectory = self._route_for_satellites(
            mission=mission,
            trajectory=trajectory,
            planned_calls=planned_calls,
        )
        planet_id = trajectory.planet_ids[0]
        satellite_invocations = self._invoke_satellites(
            planned_calls,
            planet_id=planet_id,
            mission_id=mission.id,
        )
        recent_history = self._format_history(prior_turns)
        context: dict[str, Any] = {}
        if recent_history:
            context["recent_conversation"] = recent_history
        if satellite_invocations:
            context["verified_satellite_results"] = json.dumps(
                [
                    {
                        "satellite": item.satellite.id,
                        "output": item.output,
                    }
                    for item in satellite_invocations
                ],
                sort_keys=True,
                default=str,
            )
        fleet_result = self.fleet_runtime.run(
            MissionRequest(
                objective=request.message,
                specialist_id=planet_id,
                requested_effects=["read"],
                allow_network=False,
                team_size=1,
                model_id=MAC_GEMMA_PROFILE_ID,
                advisory_only=True,
                context=context,
            ),
            mission_id=mission.id,
        )
        specialist_name = fleet_result.results[0].specialist_name
        model_answer = self._clean_answer(
            fleet_result.synthesis,
            specialist_name=specialist_name,
            objective=request.message,
        )
        verified_result = self._satellite_summary(satellite_invocations)
        if satellite_invocations:
            # Exact validated tool output is authoritative. The external service
            # hosts a pretrained base model that may echo structured context, so
            # tool-backed answers omit its unverified continuation entirely.
            model_answer = ""
        answer = "\n\n".join(
            item for item in (verified_result, model_answer) if item
        ).strip()
        if not answer:
            raise ValueError("The routed Planet returned an empty answer.")
        retained = self.history.append(
            conversation_id,
            ChatTurn(role="user", content=request.message),
            ChatTurn(role="assistant", content=answer),
        )
        used_model = next(
            (item.used_model for item in fleet_result.results if item.used_model),
            None,
        )
        return WormholeChatResponse(
            conversation_id=conversation_id,
            message_id=f"message-{uuid4().hex}",
            mission_id=fleet_result.mission_id,
            status=fleet_result.status.value,
            answer=answer,
            trajectory=trajectory,
            route_context=self._route_context(
                trajectory,
                invoked_ids={item.satellite.id for item in satellite_invocations},
            ),
            satellite_invocations=satellite_invocations,
            visualization_route=fleet_result.routing,
            used_model=used_model,
            warnings=tuple(fleet_result.warnings),
            retained_turns=len(retained),
        )

    def _route_context(
        self,
        trajectory: Trajectory,
        *,
        invoked_ids: set[str] | None = None,
    ) -> ChatRouteContext:
        """Builds display context for route, overlays, tools, and external models."""

        galaxy = self.registry.get_galaxy(trajectory.galaxy_id)
        circles = tuple(
            ChatEntity(
                id=item,
                display_name=self.registry.get_circle(item).display_name,
                status="active",
            )
            for item in trajectory.circle_ids
        )
        planets = tuple(
            ChatEntity(
                id=item,
                display_name=self.registry.get_planet(item).display_name,
                status=self.registry.get_planet(item).status.value,
            )
            for item in trajectory.planet_ids
        )
        selected_circles = set(trajectory.circle_ids)
        selected_planets = set(trajectory.planet_ids)
        constellations = tuple(
            ChatEntity(
                id=item.id,
                display_name=item.display_name,
                status="connected",
            )
            for item in self.registry.constellations.values()
            if selected_circles.intersection(item.circle_ids)
            and any(
                node.kind is EntityKind.PLANET and node.id in selected_planets
                for node in item.nodes
            )
        )
        satellite_ids = {
            satellite_id
            for planet_id in trajectory.planet_ids
            for satellite_id in self.registry.get_planet(planet_id).charter.satellite_ids
        }
        satellites = tuple(
            ChatEntity(
                id=item,
                display_name=self.registry.satellites[item].display_name,
                status=(
                    "executable"
                    if self.satellite_runtime is not None
                    and item in self.satellite_runtime.executable_ids
                    else self.registry.satellites[item].status.value
                ),
            )
            for item in sorted(satellite_ids)
            if item in self.registry.satellites
        )
        model_ids = {
            model_id
            for planet_id in trajectory.planet_ids
            for model_id in self.registry.get_planet(planet_id).charter.model_ids
        }
        rogue_stars = tuple(
            ChatEntity(
                id=item,
                display_name=self.registry.rogue_stars[item].display_name,
                status="external",
            )
            for item in sorted(model_ids)
            if item in self.registry.rogue_stars
        )
        invoked_ids = invoked_ids or set()
        return ChatRouteContext(
            galaxy=ChatEntity(
                id=galaxy.id,
                display_name=galaxy.display_name,
                status="active",
            ),
            circles=circles,
            planets=planets,
            constellations=constellations,
            available_satellites=satellites,
            invoked_satellites=tuple(
                item for item in satellites if item.id in invoked_ids
            ),
            rogue_stars=rogue_stars,
        )

    def _route_for_satellites(
        self,
        *,
        mission: Mission,
        trajectory: Trajectory,
        planned_calls: tuple[PlannedSatelliteCall, ...],
    ) -> Trajectory:
        """Keeps the route when possible or selects a capable Planet safely."""

        required = {item.satellite_id for item in planned_calls}
        if not required:
            return trajectory
        selected = self.registry.get_planet(trajectory.planet_ids[0])
        if required <= set(selected.charter.satellite_ids):
            return trajectory
        candidates = [
            planet
            for planet in self.registry.planets.values()
            if required <= set(planet.charter.satellite_ids)
        ]
        if not candidates:
            missing = ", ".join(sorted(required))
            raise ValueError(f"No Planet Charter authorizes required Satellite(s): {missing}.")
        priority = {"personal_steward": 0, "knowledge_librarian": 1}
        candidates.sort(
            key=lambda item: (
                priority.get(item.id, 2),
                item.status.value != "active",
                item.display_name.lower(),
            )
        )
        return self.wormhole.route(
            mission.model_copy(update={"preferred_planet_id": candidates[0].id})
        )

    def _invoke_satellites(
        self,
        calls: tuple[PlannedSatelliteCall, ...],
        *,
        planet_id: str,
        mission_id: str,
    ) -> tuple[SatelliteInvocation, ...]:
        """Executes planned Satellites and returns their validated outputs."""

        if not calls or self.satellite_runtime is None:
            return ()
        invocations: list[SatelliteInvocation] = []
        for call in calls:
            result = self.satellite_runtime.invoke(
                call,
                planet_id=planet_id,
                mission_id=mission_id,
            )
            satellite = self.registry.satellites[call.satellite_id]
            invocations.append(
                SatelliteInvocation(
                    satellite=ChatEntity(
                        id=satellite.id,
                        display_name=satellite.display_name,
                        status="executable",
                    ),
                    arguments=call.arguments,
                    output=dict(result.get("output", {})),
                    reason=call.reason,
                )
            )
        return tuple(invocations)

    @staticmethod
    def _format_history(turns: tuple[ChatTurn, ...]) -> str:
        """Formats the newest bounded turns for the completion prompt."""

        lines = [f"{turn.role.title()}: {turn.content}" for turn in turns[-8:]]
        return "\n".join(lines)[-8_000:]

    @staticmethod
    def _satellite_summary(
        invocations: tuple[SatelliteInvocation, ...],
    ) -> str:
        """Formats exact tool evidence ahead of probabilistic model commentary."""

        lines: list[str] = []
        for invocation in invocations:
            identifier = invocation.satellite.id
            output = invocation.output
            if identifier == "calculate":
                lines.append(
                    f"Verified by Calculate Satellite: {output.get('expression')} = "
                    f"{output.get('result')}."
                )
            elif identifier == "unit_convert":
                lines.append(
                    "Verified by Unit Convert Satellite: "
                    f"{output.get('original_value')} {output.get('from_unit')} = "
                    f"{output.get('converted_value')} {output.get('to_unit')}."
                )
            elif identifier == "memory_write":
                item = output.get("item", {})
                content = item.get("content_text") or item.get("content") or "the requested fact"
                lines.append(f"Stored by Memory Write Satellite: {content}.")
            elif identifier == "memory_search":
                memories = output.get("memories", [])
                if memories:
                    facts = [
                        str(item.get("content_text") or item.get("content") or "").strip()
                        for item in memories[:5]
                    ]
                    lines.append(
                        "Retrieved by Memory Search Satellite: "
                        + "; ".join(item for item in facts if item)
                        + "."
                    )
                else:
                    lines.append("Memory Search Satellite found no matching stored memory.")
        return "\n".join(lines)

    @staticmethod
    def _clean_answer(value: str, *, specialist_name: str, objective: str) -> str:
        """Removes the continuation prefix and truncates base-model repetition."""

        prefix = f'{specialist_name} assessment of the Mission "{objective}": '
        answer = value.removeprefix(prefix).strip()
        if prefix in answer:
            answer = answer.split(prefix, 1)[0].strip()
        return answer
